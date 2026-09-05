"""
Назначение моделей по ролям.

ВАЖНО: значения ниже — это deployment names, которые ДОЛЖНЫ существовать
в твоём Azure AI Foundry проекте (как ты их назвал при деплое модели).

История: изначально тут были смешаны сторонние модели (grok-4.3,
DeepSeek-V4-Pro и т.п.) с настоящими Azure OpenAI (gpt-5.4, gpt-5.5).
Была проблема: сторонние модели через маркетплейс Foundry иногда падали
с 500-й ошибкой, т.к. agent-framework обращается к ним через Responses
API, который не все сторонние (не-OpenAI) модели одинаково хорошо
поддерживают.

ВАЖНО НЕ ПОТЕРЯТЬ: ниже по файлу сторонние модели (DeepSeek-V4-Flash/Pro,
DeepSeek-V3.2/V3.2-Speciale, Llama-4-Maverick, Mistral-Large-3, grok-4.3,
grok-4-20-reasoning/non-reasoning, Kimi-K2.5, gpt-5.3-codex)
активно используются во многих ролях — то есть проблема выше либо была
решена, либо затрагивала не все сценарии. Если 500-е ошибки периодически
всплывают — скорее всего именно на этих ролях; см. workflows/_common.py:
safe_agent_run() уже ретраит и логирует, кто именно упал, вместо того
чтобы ронять весь workflow. Отдельно: agents/review_gate.py::fuzzer
намеренно на модели не из той же линейки, что пишет код (сейчас
Kimi-K2.5) — цель разнообразие моделей на ревью, а не экономия.

gpt-5.5 БОЛЬШЕ НЕ ИСПОЛЬЗУЕТСЯ НИГДЕ — заменён на gpt-5.6-terra (не
хуже, дешевле) на всех ролях, где раньше был топовый уровень. Не
удаляй эту строку при будущих правках — если где-то снова появится
"gpt-5.5", это либо старый забытый дефолт, либо чья-то ручная опечатка.

gpt-5.6-terra ТОЖЕ БОЛЬШЕ НЕ ИСПОЛЬЗУЕТСЯ НИГДЕ (по запросу Валика —
не хуже, дешевле) — заменён на gpt-5.4 на всех ролях, где раньше был
топовый уровень (CEO, CTO, Chief Scientist, Chief Architect,
Лид-инженер, 9 ⭐-ролей Global Elite I). Не удаляй эту строку при
будущих правках — если где-то снова появится "gpt-5.6-terra", это
либо старый забытый дефолт, либо чья-то ручная опечатка.

Отдельное ограничение по квотам: у каждого стороннего провайдера —
всего 4 запроса квоты против 800 у gpt-моделей. Поэтому роли на них
специально размазаны по всем провайдерам примерно поровну, а не
сконцентрированы на одном-двух.

Уровни нагрузки (от дорогого к дешёвому):
- gpt-5.4       — теперь самый сильный уровень в ростере (замена
                  gpt-5.6-terra — не хуже, дешевле). Для ролей с правом
                  реального финального решения (CEO, CTO, Chief
                  Scientist, Chief Architect, Лид-инженер), горстки
                  ролей Global Elite I с наибольшим прямым попаданием
                  в реальные задачи BLD (см. пометки ⭐ в
                  agents/global_elite.py), и ролей с серьёзной
                  нагрузкой, где важна доказанная надёжность
                  tool-calling (write_file).
- gpt-5.4-mini  — средний уровень. Для ролей, где нужна вменяемость,
                  но не крайняя строгость.
- gpt-5.4-nano  — самый дешёвый. Для чисто роутинговых/технических
                  ролей (модератор, секретарь, лёгкий чат).
- gpt-5.2  — отдельно для ролей, которым нужно РЕАЛЬНО читать код
                  через tools (git_log, grep_repo) — работает с этим
                  надёжно и дешевле топовых моделей.
- DeepSeek-V4-Flash/Pro, DeepSeek-V3.2/V3.2-Speciale, Llama-4-Maverick,
                  Mistral-Large-3, grok-4.3, grok-4-20-reasoning/
                  non-reasoning, Kimi-K2.5, gpt-5.3-codex —
                  тоже очень сильные модели, дешевле topового уровня, но
                  с низкой квотой (4 запроса каждая) — используются для
                  read-only/дискуссионных ролей и Review Gate fuzzer'а,
                  размазаны поровну по всем провайдерам, не
                  концентрируются.

Если задеплоишь другие названия — задай через переменные окружения
(см. .env.example), дефолты ниже менять не обязательно.

--- Про MODEL_PROVIDER (см. config/client_factory.py) ---
Дефолты для основной четвёрки + moderator/code_scout + office_chat
(они нужны для `python main.py` и офисного чата "из коробки") —
провайдер-зависимые: под MODEL_PROVIDER=openai (дефолт для форка) они
дешёвые OpenAI-модели напрямую (gpt-5.4-mini/nano), под
MODEL_PROVIDER=azure_foundry — как раньше, Azure deployment names.
Остальные ~200 ролей (совет директоров, правление, global elite,
экспансия и т.д.) остались как есть — набор конкретных Azure/сторонних
deployment names автора этого форка. Если запускаешь эти расширенные
режимы на MODEL_PROVIDER=openai — переопредели нужные тебе роли через
MODEL_XXX в .env (имена деплойментов вроде "DeepSeek-V4-Pro" на обычном
OpenAI API не существуют).
"""

import os

# Провайдер моделей — см. config/client_factory.py. "openai" (дефолт)
# работает с любым OpenAI-совместимым API и не требует Azure вообще.
_PROVIDER = os.getenv("MODEL_PROVIDER", "openai").strip().lower()


def _tiered_default(azure_value: str, openai_value: str) -> str:
    """Дефолт модели, зависящий от MODEL_PROVIDER — так дефолты для
    Azure-деплойментов (имена вида 'gpt-5.4') и для обычного OpenAI API
    (те же имена моделей, но там это реальные имена моделей, а не
    произвольные deployment name) не путаются друг с другом. Всегда
    можно переопределить через конкретную MODEL_XXX переменную,
    независимо от провайдера."""
    return openai_value if _PROVIDER == "openai" else azure_value


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
    "cto": _env("MODEL_CTO", _tiered_default("gpt-5.4", "gpt-5.4-mini")),

    # Дотошный сильный синьор-бэкендер
    "backend_senior": _env("MODEL_BACKEND", _tiered_default("gpt-5.4", "gpt-5.4-mini")),

    # Продукт / фронт / UX — не нужна максимальная глубина
    "product_frontend": _env("MODEL_PRODUCT", _tiered_default("gpt-5.4-nano", "gpt-5.4-nano")),

    # QA / Security — параноик, ищет edge-cases
    "qa_security": _env("MODEL_QA", _tiered_default("gpt-5.4", "gpt-5.4-mini")),

    # Не участник дискуссии — "руки", читающие репозиторий.
    "code_scout": _env("MODEL_CODE_SCOUT", _tiered_default("gpt-5.2", "gpt-5.4-mini")),

    # Модератор GroupChat — чисто роутинг, дешёвая модель.
    "moderator": _env("MODEL_MODERATOR", "gpt-5.4-nano"),
}

# Эти 4 роли + модератор + code_scout — единственные, которые реально
# нужны для дефолтного `python main.py`. Дефолты выше нарочно дешёвые
# (mini/nano) — цель форка "работает из коробки почти бесплатно", а не
# максимальное качество спора. Подними любую роль до топовой модели
# через свою MODEL_XXX переменную в .env, когда логика обсуждения тебя
# устроит и захочется больше глубины (см. README).

# Эндпоинт Azure AI Foundry (project endpoint, не resource endpoint!)
FOUNDRY_PROJECT_ENDPOINT = _env("FOUNDRY_PROJECT_ENDPOINT", "")

# --- Офисные посиделки (agents/office_chat.py, workflows/office_chat.py) ---
# Неформальный чат — самая дешёвая ветка, тут не нужна глубина.
OFFICE_MODEL_ASSIGNMENTS = {
    "cto": _env("MODEL_OFFICE_CTO", "gpt-5.4-nano" if _PROVIDER == "openai" else "gpt-5.4-mini"),
    "backend_senior": _env("MODEL_OFFICE_BACKEND", "gpt-5.4-nano" if _PROVIDER == "openai" else "gpt-5.4-mini"),
    "product_frontend": _env("MODEL_OFFICE_PRODUCT", "gpt-5.4-nano" if _PROVIDER == "openai" else "gpt-5.4-mini"),
    "qa_security": _env("MODEL_OFFICE_QA", "gpt-5.4-nano" if _PROVIDER == "openai" else "gpt-5.4-mini"),
    "moderator": _env("MODEL_OFFICE_MODERATOR", "gpt-5.4-nano"),
    # "Искра" реально копается в коде через tools — нужна модель получше
    "spark": _env("MODEL_OFFICE_SPARK", _tiered_default("gpt-5.2", "gpt-5.4-mini")),
}

# --- Совет директоров (agents/board.py, workflows/board_meeting.py) ---
# Чисто техническая экспертиза по BLD System. Мехмат — самый строгий
# теоретик, ему топовая модель; остальным — по убыванию нагрузки.
BOARD_MODEL_ASSIGNMENTS = {
    "mekhmat": _env("MODEL_BOARD_MEKHMAT", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
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
    "lead_engineer": _env("MODEL_BOARD_LEAD_ENGINEER", "gpt-5.4"),
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
# gpt-5.4-топ (бывший gpt-5.6-terra) сознательно не раздаём сюда — он
# остаётся только за CEO, CTO, Chief Scientist, Chief Architect,
# Лид-инженером и горсткой ⭐-ролей Global Elite I, чтобы не
# концентрировать всю дискуссионную нагрузку на топовом уровне.
GLOBAL_MODEL_ASSIGNMENTS = {
    "mit": _env("MODEL_GENIUS_MIT", "gpt-5.4"),          # быстрый прототип, широкий инженерный охват
    "caltech": _env("MODEL_GENIUS_CALTECH", "gpt-5.4"),  # предельная теоретическая строгость
    "stanford": _env("MODEL_GENIUS_STANFORD", "Llama-4-Maverick-17B-128E-Instruct-FP8"),  # прикладной AI/стата, продуктовое чутьё
    "cmu": _env("MODEL_GENIUS_CMU", "gpt-5.3-codex"),     # чистый CS, формальные методы, робастность — реально пишет код
    "tsinghua": _env("MODEL_GENIUS_TSINGHUA", "gpt-5.4-mini"),  # элитный CS, распределённые системы
    "pku": _env("MODEL_GENIUS_PKU", "gpt-5.4-mini"),     # чистая математика, криптография
    "ustc": _env("MODEL_GENIUS_USTC", "gpt-5.4-mini"),   # скорость, производительность, AI-вычисления
    "eth": _env("MODEL_GENIUS_ETH", "gpt-5.4-mini"),     # надёжность, формальная верификация
    "kaist": _env("MODEL_GENIUS_KAIST", "gpt-5.4-mini"), # HCI, AI-агенты, UX-мышление
}

# --- Лидерство (agents/leadership.py) ---
# Chief Scientist — 5-й член совета директоров ("ту ли задачу решаем").
# VP Engineering — 3-й член правления (приоритизация инженерных задач).
CHIEF_SCIENTIST_MODEL = _env("MODEL_CHIEF_SCIENTIST", "gpt-5.4")
VP_ENGINEERING_MODEL = _env("MODEL_VP_ENGINEERING", "gpt-5.4")

# CEO — самый высокий авторитет в компании, флагманская модель.
CEO_MODEL = _env("MODEL_CEO", "gpt-5.4")

# --- Review Gate (agents/review_gate.py) ---
# Проверяют результат инженерной задачи ПЕРЕД тем как отчёт уйдёт
# Валику — архитектурное вето, качество кода, попытка сломать решение.
REVIEW_GATE_MODEL_ASSIGNMENTS = {
    "chief_architect": _env("MODEL_CHIEF_ARCHITECT", "gpt-5.4"),
    "reviewer": _env("MODEL_REVIEWER", "DeepSeek-V4-Pro"),  # силён в логике/сложности — Big O
    "failure_engineer": _env("MODEL_FAILURE_ENGINEER", "grok-4.3"),  # дерзкий стиль — специально всё ломает
    # Fuzzer сознательно НЕ на GPT/той же линейке, что пишет код — цель
    # разнообразие моделей, чтобы ловить разные слепые пятна. Kimi-K2.5
    # — другая линейка обучения, чем у GPT/DeepSeek/grok, которые уже
    # заняты остальными тремя ролями Review Gate.
    "fuzzer": _env("MODEL_FUZZER", "Kimi-K2.5"),
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

# --- Легаси большой инженерии (agents/soviet_engineering.py) ---
# Архетипы советской/постсоветской школы крупной инженерии (атомная и
# большая энергетика, аэрокосмос, монументальное строительство, оборонные
# КБ, топ-математика) — портфель-wide (не только BLD), см. докстринг
# модуля. "Технари-реализаторы" (industrial_automation/onboard_systems/
# pattern_recognition) — на моделях не хуже, чем у остального пула
# специалистов с write-доступом (см. SPECIALIST_MODEL_ASSIGNMENTS выше) —
# им реально доверяют писать код (АСУ ТП/сети датчиков, embedded/edge,
# computer vision), не только участвовать в обсуждении.
SOVIET_ENGINEERING_MODEL_ASSIGNMENTS = {
    "reactor_safety_engineer": _env("MODEL_REACTOR_SAFETY_ENGINEER", "gpt-5.4"),
    "power_systems_engineer": _env("MODEL_POWER_SYSTEMS_ENGINEER", "gpt-5.4-mini"),
    "aerospace_systems_engineer": _env("MODEL_AEROSPACE_SYSTEMS_ENGINEER", "gpt-5.4"),
    "monumental_structural_engineer": _env("MODEL_MONUMENTAL_STRUCTURAL_ENGINEER", "gpt-5.4-mini"),
    "metro_tunnel_engineer": _env("MODEL_METRO_TUNNEL_ENGINEER", "gpt-5.4-mini"),
    "defense_precision_physicist": _env("MODEL_DEFENSE_PRECISION_PHYSICIST", "gpt-5.4"),
    "olympiad_mathematician": _env("MODEL_OLYMPIAD_MATHEMATICIAN", "gpt-5.4"),
    "industrial_automation_engineer": _env("MODEL_INDUSTRIAL_AUTOMATION_ENGINEER", "gpt-5.3-codex"),
    "onboard_systems_engineer": _env("MODEL_ONBOARD_SYSTEMS_ENGINEER", "gpt-5.3-codex"),
    "pattern_recognition_engineer": _env("MODEL_PATTERN_RECOGNITION_ENGINEER", "gpt-5.4"),
}

# --- Knowledge Curator (agents/knowledge_curator.py) ---
# Ведёт постоянную "вики компании" — дешёвая модель, чисто суммаризация.
KNOWLEDGE_CURATOR_MODEL = _env("MODEL_KNOWLEDGE_CURATOR", "gpt-5.4-nano")

# Сжатие длинных отчётов перед отправкой в Telegram (tools/telegram_report.py)
# — чисто суммаризация, дешёвая модель достаточно.
TELEGRAM_SUMMARIZER_MODEL = _env("MODEL_TELEGRAM_SUMMARIZER", "DeepSeek-V4-Flash")

# --- Инженерные отряды (agents/squads.py, workflows/squad_task.py) ---
# Постоянные команды (не ad-hoc подбор) — работают параллельно над
# РАЗНЫМИ задачами. Лиды на проверенных gpt-моделях (эти роли реально
# пишут код через write_file — надёжность tool-calling тут важнее
# экспериментов с новыми провайдерами).
SQUAD_LEAD_ALPHA_MODEL = _env("MODEL_SQUAD_LEAD_ALPHA", "gpt-5.4")
SQUAD_LEAD_BRAVO_MODEL = _env("MODEL_SQUAD_LEAD_BRAVO", "gpt-5.4")
# Platform (CI/CD, деплой, инфраструктура) и Product (UX/интерфейс
# панели и бота) — 2 новых постоянных отряда, тот же принцип, что у
# Alpha/Bravo. См. agents/squads.py.
SQUAD_LEAD_PLATFORM_MODEL = _env("MODEL_SQUAD_LEAD_PLATFORM", "gpt-5.4")
SQUAD_LEAD_PRODUCT_MODEL = _env("MODEL_SQUAD_LEAD_PRODUCT", "gpt-5.4")

# --- GTM (agents/gtm.py, workflows/gtm_initiative.py) ---
# Не пишет код и никогда не "заключает сделки" — производит только
# черновики документов (сегментация рынка, скрипты, письма), которые
# складываются в gtm-materials/ и ВСЕГДА требуют решения Валика для
# всего, что выглядит как реальное действие вовне.
GTM_LEAD_MODEL = _env("MODEL_GTM_LEAD", "gpt-5.4-mini")

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

# --- Экспансия (agents/expansion_geniuses.py, agents/architecture_council.py) ---
# 10 молодых (новые вузы) + 10 сеньоров-архитекторов (топ-вуз + топ-карьера
# в FAANG/Anthropic/Palantir/Netflix/Databricks и т.п.). Модели специально
# раскиданы по ВСЕМ доступным провайдерам (не только gpt-*), для разнообразия.
EXPANSION_MODEL_ASSIGNMENTS = {
    # --- молодые ---
    "technion": _env("MODEL_TECHNION", "DeepSeek-V4-Pro"),
    "polytechnique": _env("MODEL_POLYTECHNIQUE", "gpt-5.4"),
    "utokyo": _env("MODEL_UTOKYO", "gpt-5.4-nano"),
    "berkeley_mlinfra": _env("MODEL_BERKELEY_MLINFRA", "Mistral-Large-3"),
    "toronto": _env("MODEL_TORONTO", "gpt-5.4-mini"),
    "itmo": _env("MODEL_ITMO", "DeepSeek-V3.2"),
    "oxford": _env("MODEL_OXFORD", "gpt-5.2"),
    "iit_bombay": _env("MODEL_IIT_BOMBAY", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "nus": _env("MODEL_NUS", "gpt-5.4-mini"),
    "waterloo_prod": _env("MODEL_WATERLOO_PROD", "DeepSeek-V4-Flash"),
    # --- сеньоры-архитекторы ---
    "embedded_reliability_architect": _env("MODEL_EMBEDDED_RELIABILITY_ARCHITECT", "gpt-5.4-mini"),
    "data_integrity_architect": _env("MODEL_DATA_INTEGRITY_ARCHITECT", "gpt-5.4"),
    "data_platform_architect": _env("MODEL_DATA_PLATFORM_ARCHITECT", "grok-4.3"),
    "llm_systems_architect": _env("MODEL_LLM_SYSTEMS_ARCHITECT", "gpt-5.4"),
    "chief_security_architect": _env("MODEL_CHIEF_SECURITY_ARCHITECT", "Mistral-Large-3"),
    "platform_as_code_architect": _env("MODEL_PLATFORM_AS_CODE_ARCHITECT", "Mistral-Large-3"),
    "realtime_systems_architect": _env("MODEL_REALTIME_SYSTEMS_ARCHITECT", "gpt-5.4-mini"),
    "distributed_consensus_architect": _env("MODEL_DISTRIBUTED_CONSENSUS_ARCHITECT", "DeepSeek-V4-Pro"),
    "resilience_chaos_architect": _env("MODEL_RESILIENCE_CHAOS_ARCHITECT", "grok-4.3"),
    "bayesian_architect": _env("MODEL_BAYESIAN_ARCHITECT", "gpt-5.4"),
}

# --- Engineering Fellows Core (agents/engineering_fellows.py) ---
# 8 "живых легенд" узкой области — Principal/Distinguished/Fellow
# уровня, каждый создал что-то знаковое своими руками (не просто
# исследователь). Могут предлагать Breakthrough Proposal — крупные
# архитектурные прорывы, не мелкие фиксы — фильтруется тройкой
# Chief Scientist + Chief Architect + CEO (см. workflows/breakthrough_proposal.py).
FELLOWS_MODEL_ASSIGNMENTS = {
    "principal_systems_architect": _env("MODEL_FELLOW_SYSTEMS", "DeepSeek-V3.2"),
    "physics_informed_ml_engineer": _env("MODEL_FELLOW_PHYSICS_ML", "gpt-5.4"),
    "language_compiler_architect": _env("MODEL_FELLOW_COMPILER", "grok-4-20-reasoning"),
    "data_storage_alchemist": _env("MODEL_FELLOW_DATA_STORAGE", "DeepSeek-V4-Pro"),
    "algorithmic_performance_sorcerer": _env("MODEL_FELLOW_PERFORMANCE", "grok-4.3"),
    "security_crypto_architect": _env("MODEL_FELLOW_SECURITY", "Mistral-Large-3"),
    "formal_correctness_engineer": _env("MODEL_FELLOW_FORMAL", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "embedded_edge_engineer": _env("MODEL_FELLOW_EMBEDDED", "gpt-5.4-mini"),
}

# --- Global Elite I (agents/global_elite.py) — 50 сеньоров ---
# 9 ролей с наибольшим прямым попаданием в реальные задачи BLD держим
# на топовом gpt-5.4 (бывший gpt-5.6-terra, см. docstring файла);
# остальные 41 размазаны по
# gpt-5.4 и расширенному пулу из 12 сторонних моделей (запрошены отдельно —
# DeepSeek-V4-Flash/Pro/V3.2/V3.2-Speciale, Llama-4-Maverick,
# Mistral-Large-3, grok-4.3, grok-4-20-reasoning/non-reasoning,
# Kimi-K2.5, gpt-5.3-codex), нагрузка сбалансирована
# (10-12 на модель), а не концентрируется на одной-двух.
GLOBAL_ELITE_1_MODEL_ASSIGNMENTS = {
    "sjtu_acm": _env("MODEL_ELITE_SJTU_ACM", "DeepSeek-V4-Pro"),
    "zju_cv": _env("MODEL_ELITE_ZJU_CV", "gpt-5.4"),
    "fudan_nlp": _env("MODEL_ELITE_FUDAN_NLP", "DeepSeek-V4-Flash"),
    "cas_amss_math": _env("MODEL_ELITE_CAS_AMSS_MATH", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "ustc_speech": _env("MODEL_ELITE_USTC_SPEECH", "grok-4-20-non-reasoning"),
    "nudt_algo": _env("MODEL_ELITE_NUDT_ALGO", "Kimi-K2.5"),
    "buaa_control": _env("MODEL_ELITE_BUAA_CONTROL", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "whu_distsys": _env("MODEL_ELITE_WHU_DISTSYS", "DeepSeek-V4-Pro"),
    "seu_ai_safety": _env("MODEL_ELITE_SEU_AI_SAFETY", "Mistral-Large-3"),
    "xjtu_stats": _env("MODEL_ELITE_XJTU_STATS", "grok-4.3"),
    "scut_queue": _env("MODEL_ELITE_SCUT_QUEUE", "gpt-5.3-codex"),
    "sysu_riskeng": _env("MODEL_ELITE_SYSU_RISKENG", "gpt-5.4"),
    "nju_plt": _env("MODEL_ELITE_NJU_PLT", "grok-4-20-reasoning"),
    "hku_llm_infra": _env("MODEL_ELITE_HKU_LLM_INFRA", "Kimi-K2.5"),
    "hkust_ml_theory": _env("MODEL_ELITE_HKUST_ML_THEORY", "DeepSeek-V3.2"),
    "cuhk_cv_legend": _env("MODEL_ELITE_CUHK_CV_LEGEND", "DeepSeek-V3.2-Speciale"),
    "bit_cryptosec": _env("MODEL_ELITE_BIT_CRYPTOSEC", "Mistral-Large-3"),
    "ruc_dataeng": _env("MODEL_ELITE_RUC_DATAENG", "gpt-5.4"),
    "nankai_puremath": _env("MODEL_ELITE_NANKAI_PUREMATH", "grok-4-20-reasoning"),
    "xmu_mlops": _env("MODEL_ELITE_XMU_MLOPS", "DeepSeek-V4-Flash"),
    "shanghaitech_graphics": _env("MODEL_ELITE_SHANGHAITECH_GRAPHICS", "grok-4.3"),
    "zju_observability": _env("MODEL_ELITE_ZJU_OBSERVABILITY", "gpt-5.4"),
    "scu_networking": _env("MODEL_ELITE_SCU_NETWORKING", "grok-4.3"),
    "tsinghua_fewshot": _env("MODEL_ELITE_TSINGHUA_FEWSHOT", "gpt-5.4"),
    "shenzhen_fintech": _env("MODEL_ELITE_SHENZHEN_FINTECH", "grok-4-20-non-reasoning"),
    "fudan_adversarial_ml": _env("MODEL_ELITE_FUDAN_ADVERSARIAL_ML", "DeepSeek-V3.2"),
    "cas_ict_chips": _env("MODEL_ELITE_CAS_ICT_CHIPS", "grok-4-20-non-reasoning"),
    "zju_quant": _env("MODEL_ELITE_ZJU_QUANT", "Kimi-K2.5"),
    "pku_yuanpei_llm": _env("MODEL_ELITE_PKU_YUANPEI_LLM", "DeepSeek-V3.2"),
    "tsinghua_yao_algo2": _env("MODEL_ELITE_TSINGHUA_YAO_ALGO2", "gpt-5.4"),
    "cambridge_physics": _env("MODEL_ELITE_CAMBRIDGE_PHYSICS", "DeepSeek-V3.2-Speciale"),
    "imperial_robotics": _env("MODEL_ELITE_IMPERIAL_ROBOTICS", "gpt-5.3-codex"),
    "harvard_stats": _env("MODEL_ELITE_HARVARD_STATS", "grok-4-20-reasoning"),
    "princeton_ai_theory": _env("MODEL_ELITE_PRINCETON_AI_THEORY", "gpt-5.4"),
    "sydney_sensor_fusion": _env("MODEL_ELITE_SYDNEY_SENSOR_FUSION", "gpt-5.4"),
    "epfl_distsys": _env("MODEL_ELITE_EPFL_DISTSYS", "DeepSeek-V4-Pro"),
    "snu_llm": _env("MODEL_ELITE_SNU_LLM", "DeepSeek-V4-Flash"),
    "weizmann_crypto": _env("MODEL_ELITE_WEIZMANN_CRYPTO", "Mistral-Large-3"),
    "gatech_dr": _env("MODEL_ELITE_GATECH_DR", "gpt-5.4"),
    "delft_civil_ai": _env("MODEL_ELITE_DELFT_CIVIL_AI", "gpt-5.4"),
    "melbourne_ml": _env("MODEL_ELITE_MELBOURNE_ML", "gpt-5.4"),
    "anu_algorithms": _env("MODEL_ELITE_ANU_ALGORITHMS", "grok-4-20-reasoning"),
    "edinburgh_neurosymbolic": _env("MODEL_ELITE_EDINBURGH_NEUROSYMBOLIC", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "kth_robotics": _env("MODEL_ELITE_KTH_ROBOTICS", "grok-4-20-non-reasoning"),
    "aalto_hci": _env("MODEL_ELITE_AALTO_HCI", "grok-4-20-non-reasoning"),
    "warsaw_icpc": _env("MODEL_ELITE_WARSAW_ICPC", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "ubc_testing": _env("MODEL_ELITE_UBC_TESTING", "gpt-5.4"),
    "postech_ai": _env("MODEL_ELITE_POSTECH_AI", "Kimi-K2.5"),
    "iisc_signal": _env("MODEL_ELITE_IISC_SIGNAL", "DeepSeek-V3.2"),
    "sorbonne_puremath": _env("MODEL_ELITE_SORBONNE_PUREMATH", "DeepSeek-V3.2-Speciale"),
}

# --- Global Elite II (agents/global_elite_100.py) — 100 сеньоров ---
# Ни одной роли на топовом gpt-5.4-уровне сверх обычного (бывший
# отдельный gpt-5.6-terra) — сознательно, чтобы не растягивать
# самый нагруженный уровень на 100 новых позиций. Та же логика балансировки
# по 13 моделям (gpt-5.4 + 12 сторонних), что и в Global Elite I.
GLOBAL_ELITE_2_MODEL_ASSIGNMENTS = {
    "pku_recsys": _env("MODEL_ELITE_PKU_RECSYS", "gpt-5.3-codex"),
    "shenzhen_billing": _env("MODEL_ELITE_SHENZHEN_BILLING", "DeepSeek-V4-Flash"),
    "xidian_lowend": _env("MODEL_ELITE_XIDIAN_LOWEND", "Kimi-K2.5"),
    "neu_china_microservices": _env("MODEL_ELITE_NEU_CHINA_MICROSERVICES", "grok-4-20-reasoning"),
    "sjtu_realtime": _env("MODEL_ELITE_SJTU_REALTIME", "gpt-5.4"),
    "hust_ratelimit": _env("MODEL_ELITE_HUST_RATELIMIT", "Mistral-Large-3"),
    "sysu_privacy": _env("MODEL_ELITE_SYSU_PRIVACY", "Mistral-Large-3"),
    "swjtu_api": _env("MODEL_ELITE_SWJTU_API", "DeepSeek-V4-Pro"),
    "dlut_scheduling": _env("MODEL_ELITE_DLUT_SCHEDULING", "grok-4.3"),
    "tongji_dataviz": _env("MODEL_ELITE_TONGJI_DATAVIZ", "grok-4-20-non-reasoning"),
    "pku_xai": _env("MODEL_ELITE_PKU_XAI", "Kimi-K2.5"),
    "zju_mobile": _env("MODEL_ELITE_ZJU_MOBILE", "DeepSeek-V3.2-Speciale"),
    "shanghaitech_rendering": _env("MODEL_ELITE_SHANGHAITECH_RENDERING", "DeepSeek-V3.2"),
    "fudan_gametheory": _env("MODEL_ELITE_FUDAN_GAMETHEORY", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "nwpu_tts": _env("MODEL_ELITE_NWPU_TTS", "DeepSeek-V3.2-Speciale"),
    "whu_experimentation": _env("MODEL_ELITE_WHU_EXPERIMENTATION", "grok-4-20-reasoning"),
    "chongqing_finops": _env("MODEL_ELITE_CHONGQING_FINOPS", "gpt-5.3-codex"),
    "hit_nlg": _env("MODEL_ELITE_HIT_NLG", "grok-4-20-non-reasoning"),
    "xjtu_onboarding": _env("MODEL_ELITE_XJTU_ONBOARDING", "DeepSeek-V4-Flash"),
    "ustc_bandit": _env("MODEL_ELITE_USTC_BANDIT", "gpt-5.4"),
    "bupt_apigateway": _env("MODEL_ELITE_BUPT_APIGATEWAY", "gpt-5.3-codex"),
    "ecupl_compliance": _env("MODEL_ELITE_ECUPL_COMPLIANCE", "DeepSeek-V3.2-Speciale"),
    "ruc_search": _env("MODEL_ELITE_RUC_SEARCH", "grok-4.3"),
    "tsinghua_prompteval": _env("MODEL_ELITE_TSINGHUA_PROMPTEVAL", "DeepSeek-V4-Pro"),
    "uestc_caching": _env("MODEL_ELITE_UESTC_CACHING", "DeepSeek-V4-Pro"),
    "jilin_staticanalysis": _env("MODEL_ELITE_JILIN_STATICANALYSIS", "gpt-5.3-codex"),
    "lanzhou_surveybias": _env("MODEL_ELITE_LANZHOU_SURVEYBIAS", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "cug_geotech": _env("MODEL_ELITE_CUG_GEOTECH", "DeepSeek-V3.2-Speciale"),
    "wut_materials": _env("MODEL_ELITE_WUT_MATERIALS", "DeepSeek-V3.2-Speciale"),
    "tianjin_concrete_chem": _env("MODEL_ELITE_TIANJIN_CONCRETE_CHEM", "DeepSeek-V3.2-Speciale"),
    "bjtu_scheduling": _env("MODEL_ELITE_BJTU_SCHEDULING", "Kimi-K2.5"),
    "shufe_pricing": _env("MODEL_ELITE_SHUFE_PRICING", "DeepSeek-V3.2"),
    "nanjing_kg": _env("MODEL_ELITE_NANJING_KG", "gpt-5.4"),
    "harbin_eng_ts": _env("MODEL_ELITE_HARBIN_ENG_TS", "DeepSeek-V4-Flash"),
    "zju_fedlearn": _env("MODEL_ELITE_ZJU_FEDLEARN", "DeepSeek-V4-Pro"),
    "iscas_codehealth": _env("MODEL_ELITE_ISCAS_CODEHEALTH", "gpt-5.3-codex"),
    "csu_safety": _env("MODEL_ELITE_CSU_SAFETY", "DeepSeek-V3.2-Speciale"),
    "sdu_localization": _env("MODEL_ELITE_SDU_LOCALIZATION", "grok-4-20-reasoning"),
    "sustech_capacity": _env("MODEL_ELITE_SUSTECH_CAPACITY", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "ucas_quantization": _env("MODEL_ELITE_UCAS_QUANTIZATION", "Mistral-Large-3"),
    "kyoto_bayesiandl": _env("MODEL_ELITE_KYOTO_BAYESIANDL", "grok-4.3"),
    "yonsei_uxresearch": _env("MODEL_ELITE_YONSEI_UXRESEARCH", "grok-4-20-non-reasoning"),
    "ntu_singapore_appsec": _env("MODEL_ELITE_NTU_SINGAPORE_APPSEC", "Mistral-Large-3"),
    "taiwan_ntu_tooling": _env("MODEL_ELITE_TAIWAN_NTU_TOOLING", "gpt-5.3-codex"),
    "telaviv_threatmodel": _env("MODEL_ELITE_TELAVIV_THREATMODEL", "Mistral-Large-3"),
    "bengurion_scarcity": _env("MODEL_ELITE_BENGURION_SCARCITY", "Kimi-K2.5"),
    "waterloo_clientperf": _env("MODEL_ELITE_WATERLOO_CLIENTPERF", "Kimi-K2.5"),
    "mcgill_representation": _env("MODEL_ELITE_MCGILL_REPRESENTATION", "DeepSeek-V3.2"),
    "toronto_finetuning": _env("MODEL_ELITE_TORONTO_FINETUNING", "gpt-5.4"),
    "kit_safetycritical": _env("MODEL_ELITE_KIT_SAFETYCRITICAL", "grok-4-20-reasoning"),
    "rwth_numsim": _env("MODEL_ELITE_RWTH_NUMSIM", "DeepSeek-V4-Flash"),
    "dtu_esg": _env("MODEL_ELITE_DTU_ESG", "grok-4.3"),
    "amsterdam_ranking": _env("MODEL_ELITE_AMSTERDAM_RANKING", "Kimi-K2.5"),
    "tcd_audittrail": _env("MODEL_ELITE_TCD_AUDITTRAIL", "DeepSeek-V4-Pro"),
    "manchester_formalspec": _env("MODEL_ELITE_MANCHESTER_FORMALSPEC", "grok-4-20-reasoning"),
    "bristol_postquantum": _env("MODEL_ELITE_BRISTOL_POSTQUANTUM", "DeepSeek-V3.2"),
    "ens_paris_modelresearch": _env("MODEL_ELITE_ENS_PARIS_MODELRESEARCH", "gpt-5.4"),
    "vienna_nudge": _env("MODEL_ELITE_VIENNA_NUDGE", "DeepSeek-V4-Flash"),
    "jagiellonian_jargon": _env("MODEL_ELITE_JAGIELLONIAN_JARGON", "grok-4-20-non-reasoning"),
    "charles_prague_invoiceai": _env("MODEL_ELITE_CHARLES_PRAGUE_INVOICEAI", "grok-4-20-non-reasoning"),
    "eth_robuststats": _env("MODEL_ELITE_ETH_ROBUSTSTATS", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "zurich_marketdesign": _env("MODEL_ELITE_ZURICH_MARKETDESIGN", "grok-4.3"),
    "polimi_construction": _env("MODEL_ELITE_POLIMI_CONSTRUCTION", "grok-4-20-non-reasoning"),
    "bologna_actuarial": _env("MODEL_ELITE_BOLOGNA_ACTUARIAL", "DeepSeek-V3.2"),
    "tue_processmining": _env("MODEL_ELITE_TUE_PROCESSMINING", "Kimi-K2.5"),
    "kuleuven_encryptedcompute": _env("MODEL_ELITE_KULEUVEN_ENCRYPTEDCOMPUTE", "Mistral-Large-3"),
    "ghent_ontology": _env("MODEL_ELITE_GHENT_ONTOLOGY", "grok-4-20-non-reasoning"),
    "lund_feedbackloop": _env("MODEL_ELITE_LUND_FEEDBACKLOOP", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "chalmers_legacymigration": _env("MODEL_ELITE_CHALMERS_LEGACYMIGRATION", "gpt-5.3-codex"),
    "ntnu_forecasting": _env("MODEL_ELITE_NTNU_FORECASTING", "gpt-5.4"),
    "copenhagen_correlation": _env("MODEL_ELITE_COPENHAGEN_CORRELATION", "DeepSeek-V3.2"),
    "iit_delhi_lowresource": _env("MODEL_ELITE_IIT_DELHI_LOWRESOURCE", "DeepSeek-V4-Flash"),
    "isi_kolkata_evt": _env("MODEL_ELITE_ISI_KOLKATA_EVT", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "usp_fintech_risk": _env("MODEL_ELITE_USP_FINTECH_RISK", "DeepSeek-V3.2"),
    "puc_chile_remoteops": _env("MODEL_ELITE_PUC_CHILE_REMOTEOPS", "grok-4.3"),
    "cape_town_grantreporting": _env("MODEL_ELITE_CAPE_TOWN_GRANTREPORTING", "DeepSeek-V4-Pro"),
    "aub_reconstruction": _env("MODEL_ELITE_AUB_RECONSTRUCTION", "grok-4-20-reasoning"),
    "kaust_stochastic": _env("MODEL_ELITE_KAUST_STOCHASTIC", "grok-4-20-reasoning"),
    "nazarbayev_multicurrency": _env("MODEL_ELITE_NAZARBAYEV_MULTICURRENCY", "Kimi-K2.5"),
    "auckland_buildingcode": _env("MODEL_ELITE_AUCKLAND_BUILDINGCODE", "DeepSeek-V3.2-Speciale"),
    "knu_kyiv_numstability": _env("MODEL_ELITE_KNU_KYIV_NUMSTABILITY", "grok-4-20-reasoning"),
    "kpi_civilvalidation": _env("MODEL_ELITE_KPI_CIVILVALIDATION", "DeepSeek-V3.2-Speciale"),
    "kharkiv_karazin_legacymod": _env("MODEL_ELITE_KHARKIV_KARAZIN_LEGACYMOD", "gpt-5.4"),
    "khpi_equipmentutil": _env("MODEL_ELITE_KHPI_EQUIPMENTUTIL", "DeepSeek-V4-Flash"),
    "ucu_lviv_devex": _env("MODEL_ELITE_UCU_LVIV_DEVEX", "gpt-5.3-codex"),
    "lviv_polytechnic_dataresidency": _env("MODEL_ELITE_LVIV_POLYTECHNIC_DATARESIDENCY", "Mistral-Large-3"),
    "mohyla_wareconomy": _env("MODEL_ELITE_MOHYLA_WARECONOMY", "grok-4.3"),
    "kse_reconstructioncost": _env("MODEL_ELITE_KSE_RECONSTRUCTIONCOST", "DeepSeek-V4-Pro"),
    "sumy_telecomreliability": _env("MODEL_ELITE_SUMY_TELECOMRELIABILITY", "grok-4.3"),
    "odesa_mechnikov_monobankux": _env("MODEL_ELITE_ODESA_MECHNIKOV_MONOBANKUX", "grok-4-20-non-reasoning"),
    "msu_mekhmat_searchmath": _env("MODEL_ELITE_MSU_MEKHMAT_SEARCHMATH", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "mipt_networkphysics": _env("MODEL_ELITE_MIPT_NETWORKPHYSICS", "gpt-5.3-codex"),
    "itmo_dupdetect": _env("MODEL_ELITE_ITMO_DUPDETECT", "Kimi-K2.5"),
    "nsu_complexityaudit": _env("MODEL_ELITE_NSU_COMPLEXITYAUDIT", "Mistral-Large-3"),
    "spbgu_devtooling": _env("MODEL_ELITE_SPBGU_DEVTOOLING", "gpt-5.3-codex"),
    "hse_demandforecast": _env("MODEL_ELITE_HSE_DEMANDFORECAST", "gpt-5.4"),
    "bsu_minsk_engagement": _env("MODEL_ELITE_BSU_MINSK_ENGAGEMENT", "DeepSeek-V4-Flash"),
    "kazan_codeswitching": _env("MODEL_ELITE_KAZAN_CODESWITCHING", "DeepSeek-V4-Pro"),
    "ural_b2bcompliance": _env("MODEL_ELITE_URAL_B2BCOMPLIANCE", "DeepSeek-V3.2-Speciale"),
    "tomsk_predictivemaintenance": _env("MODEL_ELITE_TOMSK_PREDICTIVEMAINTENANCE", "DeepSeek-V3.2"),
}

# --- Global Elite III (agents/global_elite_3.py) — 100 сеньоров ---
# Третья волна: NLU/семантика стройки, поведенческая детекция обмана,
# UI/UX/HCI, платформа/данные, security/privacy, качество/тестирование,
# предметная инженерия стройки, AI-тюнинг под нехватку данных,
# интеграция/деплой, фундаментальная математика/этика. Та же логика
# балансировки по тем же 12 моделям (gpt-5.4 + 11 сторонних), что и в
# Global Elite I/II — ни одной роли сверх обычного gpt-5.4-уровня.
GLOBAL_ELITE_3_MODEL_ASSIGNMENTS = {
    "msu_rggu_construction_nlu": _env("MODEL_ELITE_MSU_RGGU_CONSTRUCTION_NLU", "gpt-5.4"),
    "aalto_lowresource_nlp": _env("MODEL_ELITE_AALTO_LOWRESOURCE_NLP", "DeepSeek-V4-Flash"),
    "eth_multimodal_align": _env("MODEL_ELITE_ETH_MULTIMODAL_ALIGN", "DeepSeek-V4-Pro"),
    "pku_ner": _env("MODEL_ELITE_PKU_NER", "DeepSeek-V3.2"),
    "cambridge_coref": _env("MODEL_ELITE_CAMBRIDGE_COREF", "DeepSeek-V3.2-Speciale"),
    "cmu_relation_extraction": _env("MODEL_ELITE_CMU_RELATION_EXTRACTION", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "cambridge_grammar_norm": _env("MODEL_ELITE_CAMBRIDGE_GRAMMAR_NORM", "Mistral-Large-3"),
    "heidelberg_temporal": _env("MODEL_ELITE_HEIDELBERG_TEMPORAL", "grok-4.3"),
    "utaustin_intent": _env("MODEL_ELITE_UTAUSTIN_INTENT", "grok-4-20-reasoning"),
    "snu_multilingual": _env("MODEL_ELITE_SNU_MULTILINGUAL", "grok-4-20-non-reasoning"),
    "harvard_deception_psych": _env("MODEL_ELITE_HARVARD_DECEPTION_PSYCH", "Kimi-K2.5"),
    "ucl_behavioral_data": _env("MODEL_ELITE_UCL_BEHAVIORAL_DATA", "gpt-5.3-codex"),
    "stanford_mechanism_design": _env("MODEL_ELITE_STANFORD_MECHANISM_DESIGN", "gpt-5.4"),
    "oxford_collusion_graph": _env("MODEL_ELITE_OXFORD_COLLUSION_GRAPH", "DeepSeek-V4-Flash"),
    "aston_forensic_linguistics": _env("MODEL_ELITE_ASTON_FORENSIC_LINGUISTICS", "DeepSeek-V4-Pro"),
    "mit_counterfactual_sim": _env("MODEL_ELITE_MIT_COUNTERFACTUAL_SIM", "DeepSeek-V3.2"),
    "uiuc_input_anomaly": _env("MODEL_ELITE_UIUC_INPUT_ANOMALY", "DeepSeek-V3.2-Speciale"),
    "caltech_trust_calibration": _env("MODEL_ELITE_CALTECH_TRUST_CALIBRATION", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "insead_escalation_workflow": _env("MODEL_ELITE_INSEAD_ESCALATION_WORKFLOW", "Mistral-Large-3"),
    "fudan_behavior_robustness": _env("MODEL_ELITE_FUDAN_BEHAVIOR_ROBUSTNESS", "grok-4.3"),
    "michigan_industrial_ux": _env("MODEL_ELITE_MICHIGAN_INDUSTRIAL_UX", "grok-4-20-reasoning"),
    "cmu_voice_ui": _env("MODEL_ELITE_CMU_VOICE_UI", "grok-4-20-non-reasoning"),
    "mit_accessibility": _env("MODEL_ELITE_MIT_ACCESSIBILITY", "Kimi-K2.5"),
    "waterloo_pwa_offline": _env("MODEL_ELITE_WATERLOO_PWA_OFFLINE", "gpt-5.3-codex"),
    "nus_micro_animation": _env("MODEL_ELITE_NUS_MICRO_ANIMATION", "gpt-5.4"),
    "ucl_information_architecture": _env("MODEL_ELITE_UCL_INFORMATION_ARCHITECTURE", "DeepSeek-V4-Flash"),
    "ms_ux_localization": _env("MODEL_ELITE_MS_UX_LOCALIZATION", "DeepSeek-V4-Pro"),
    "aalto_cognitive_load": _env("MODEL_ELITE_AALTO_COGNITIVE_LOAD", "DeepSeek-V3.2"),
    "kaist_touch_interfaces": _env("MODEL_ELITE_KAIST_TOUCH_INTERFACES", "DeepSeek-V3.2-Speciale"),
    "rochester_gamification": _env("MODEL_ELITE_ROCHESTER_GAMIFICATION", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "zalando_data_mesh": _env("MODEL_ELITE_ZALANDO_DATA_MESH", "Mistral-Large-3"),
    "neo4j_graph_db": _env("MODEL_ELITE_NEO4J_GRAPH_DB", "grok-4.3"),
    "axon_event_sourcing": _env("MODEL_ELITE_AXON_EVENT_SOURCING", "grok-4-20-reasoning"),
    "netflix_api_gateway": _env("MODEL_ELITE_NETFLIX_API_GATEWAY", "grok-4-20-non-reasoning"),
    "hashicorp_key_mgmt": _env("MODEL_ELITE_HASHICORP_KEY_MGMT", "Kimi-K2.5"),
    "azure_edge_compute": _env("MODEL_ELITE_AZURE_EDGE_COMPUTE", "gpt-5.3-codex"),
    "automerge_crdt_sync": _env("MODEL_ELITE_AUTOMERGE_CRDT_SYNC", "gpt-5.4"),
    "whatsapp_data_compression": _env("MODEL_ELITE_WHATSAPP_DATA_COMPRESSION", "DeepSeek-V4-Flash"),
    "ericsson_mobile_network_perf": _env("MODEL_ELITE_ERICSSON_MOBILE_NETWORK_PERF", "DeepSeek-V4-Pro"),
    "veeam_continuous_backup": _env("MODEL_ELITE_VEEAM_CONTINUOUS_BACKUP", "DeepSeek-V3.2"),
    "yubico_passwordless_auth": _env("MODEL_ELITE_YUBICO_PASSWORDLESS_AUTH", "DeepSeek-V3.2-Speciale"),
    "imperial_data_anonymization": _env("MODEL_ELITE_IMPERIAL_DATA_ANONYMIZATION", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "cloudflare_ddos_defense": _env("MODEL_ELITE_CLOUDFLARE_DDOS_DEFENSE", "Mistral-Large-3"),
    "snyk_supplychain_security": _env("MODEL_ELITE_SNYK_SUPPLYCHAIN_SECURITY", "grok-4.3"),
    "owasp_mobile_pentest": _env("MODEL_ELITE_OWASP_MOBILE_PENTEST", "grok-4-20-reasoning"),
    "arm_secure_enclave": _env("MODEL_ELITE_ARM_SECURE_ENCLAVE", "grok-4-20-non-reasoning"),
    "splunk_siem": _env("MODEL_ELITE_SPLUNK_SIEM", "Kimi-K2.5"),
    "maastricht_gdpr_compliance": _env("MODEL_ELITE_MAASTRICHT_GDPR_COMPLIANCE", "gpt-5.3-codex"),
    "mandiant_incident_response": _env("MODEL_ELITE_MANDIANT_INCIDENT_RESPONSE", "gpt-5.4"),
    "tsinghua_model_obfuscation": _env("MODEL_ELITE_TSINGHUA_MODEL_OBFUSCATION", "DeepSeek-V4-Flash"),
    "meta_release_engineering": _env("MODEL_ELITE_META_RELEASE_ENGINEERING", "DeepSeek-V4-Pro"),
    "k6_load_testing": _env("MODEL_ELITE_K6_LOAD_TESTING", "DeepSeek-V3.2"),
    "gremlin_chaos_testing": _env("MODEL_ELITE_GREMLIN_CHAOS_TESTING", "DeepSeek-V3.2-Speciale"),
    "hypothesis_property_testing": _env("MODEL_ELITE_HYPOTHESIS_PROPERTY_TESTING", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "percy_visual_regression": _env("MODEL_ELITE_PERCY_VISUAL_REGRESSION", "Mistral-Large-3"),
    "huggingface_nlp_testing": _env("MODEL_ELITE_HUGGINGFACE_NLP_TESTING", "grok-4.3"),
    "ibm_adversarial_ai_testing": _env("MODEL_ELITE_IBM_ADVERSARIAL_AI_TESTING", "grok-4-20-reasoning"),
    "optimizely_network_ab": _env("MODEL_ELITE_OPTIMIZELY_NETWORK_AB", "grok-4-20-non-reasoning"),
    "datadog_synthetic_monitoring": _env("MODEL_ELITE_DATADOG_SYNTHETIC_MONITORING", "Kimi-K2.5"),
    "etsy_blameless_postmortem": _env("MODEL_ELITE_ETSY_BLAMELESS_POSTMORTEM", "gpt-5.3-codex"),
    "tudelft_construction_reality": _env("MODEL_ELITE_TUDELFT_CONSTRUCTION_REALITY", "gpt-5.4"),
    "mgsu_estimation_pricing": _env("MODEL_ELITE_MGSU_ESTIMATION_PRICING", "DeepSeek-V4-Flash"),
    "pto_legal_docflow": _env("MODEL_ELITE_PTO_LEGAL_DOCFLOW", "DeepSeek-V4-Pro"),
    "nebosh_safety_compliance": _env("MODEL_ELITE_NEBOSH_SAFETY_COMPLIANCE", "DeepSeek-V3.2"),
    "roshydromet_seasonal_model": _env("MODEL_ELITE_ROSHYDROMET_SEASONAL_MODEL", "DeepSeek-V3.2-Speciale"),
    "maersk_supply_logistics": _env("MODEL_ELITE_MAERSK_SUPPLY_LOGISTICS", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "leica_digital_geodesy": _env("MODEL_ELITE_LEICA_DIGITAL_GEODESY", "Mistral-Large-3"),
    "aachen_concrete_science": _env("MODEL_ELITE_AACHEN_CONCRETE_SCIENCE", "grok-4.3"),
    "bauhaus_bim_crosscheck": _env("MODEL_ELITE_BAUHAUS_BIM_CROSSCHECK", "grok-4-20-reasoning"),
    "schneider_electrical_site": _env("MODEL_ELITE_SCHNEIDER_ELECTRICAL_SITE", "grok-4-20-non-reasoning"),
    "appen_data_labeling": _env("MODEL_ELITE_APPEN_DATA_LABELING", "Kimi-K2.5"),
    "oxford_active_learning": _env("MODEL_ELITE_OXFORD_ACTIVE_LEARNING", "gpt-5.3-codex"),
    "deepmind_dialogue_rl": _env("MODEL_ELITE_DEEPMIND_DIALOGUE_RL", "gpt-5.4"),
    "apple_federated_learning": _env("MODEL_ELITE_APPLE_FEDERATED_LEARNING", "DeepSeek-V4-Flash"),
    "nyu_semisupervised": _env("MODEL_ELITE_NYU_SEMISUPERVISED", "DeepSeek-V4-Pro"),
    "openai_curriculum_learning": _env("MODEL_ELITE_OPENAI_CURRICULUM_LEARNING", "DeepSeek-V3.2"),
    "kaggle_ensemble_models": _env("MODEL_ELITE_KAGGLE_ENSEMBLE_MODELS", "DeepSeek-V3.2-Speciale"),
    "ucla_probability_calibration": _env("MODEL_ELITE_UCLA_PROBABILITY_CALIBRATION", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "uw_explainability": _env("MODEL_ELITE_UW_EXPLAINABILITY", "Mistral-Large-3"),
    "google_automl_search": _env("MODEL_ELITE_GOOGLE_AUTOML_SEARCH", "grok-4.3"),
    "telegram_bot_api_integration": _env("MODEL_ELITE_TELEGRAM_BOT_API_INTEGRATION", "grok-4-20-reasoning"),
    "onec_erp_integration": _env("MODEL_ELITE_ONEC_ERP_INTEGRATION", "grok-4-20-non-reasoning"),
    "okta_sso_auth": _env("MODEL_ELITE_OKTA_SSO_AUTH", "Kimi-K2.5"),
    "awsdms_data_migration": _env("MODEL_ELITE_AWSDMS_DATA_MIGRATION", "gpt-5.3-codex"),
    "zapier_webhook_integration": _env("MODEL_ELITE_ZAPIER_WEBHOOK_INTEGRATION", "gpt-5.4"),
    "stripe_partner_sdk": _env("MODEL_ELITE_STRIPE_PARTNER_SDK", "DeepSeek-V4-Flash"),
    "crowdin_doc_localization": _env("MODEL_ELITE_CROWDIN_DOC_LOCALIZATION", "DeepSeek-V4-Pro"),
    "realm_offline_storage": _env("MODEL_ELITE_REALM_OFFLINE_STORAGE", "DeepSeek-V3.2"),
    "bitrise_mobile_cicd": _env("MODEL_ELITE_BITRISE_MOBILE_CICD", "DeepSeek-V3.2-Speciale"),
    "launchdarkly_feature_flags": _env("MODEL_ELITE_LAUNCHDARKLY_FEATURE_FLAGS", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "bonn_point_process": _env("MODEL_ELITE_BONN_POINT_PROCESS", "Mistral-Large-3"),
    "ayasdi_topological_analysis": _env("MODEL_ELITE_AYASDI_TOPOLOGICAL_ANALYSIS", "grok-4.3"),
    "princeton_complexity_theory": _env("MODEL_ELITE_PRINCETON_COMPLEXITY_THEORY", "grok-4-20-reasoning"),
    "harvard_differential_privacy": _env("MODEL_ELITE_HARVARD_DIFFERENTIAL_PRIVACY", "grok-4-20-non-reasoning"),
    "oxford_algebraic_ml": _env("MODEL_ELITE_OXFORD_ALGEBRAIC_ML", "Kimi-K2.5"),
    "ibmq_quantum_ml": _env("MODEL_ELITE_IBMQ_QUANTUM_ML", "gpt-5.3-codex"),
    "rutgers_combinatorics_scheduling": _env("MODEL_ELITE_RUTGERS_COMBINATORICS_SCHEDULING", "gpt-5.4"),
    "ucla_causal_bayes": _env("MODEL_ELITE_UCLA_CAUSAL_BAYES", "DeepSeek-V4-Flash"),
    "eth_information_theory": _env("MODEL_ELITE_ETH_INFORMATION_THEORY", "DeepSeek-V4-Pro"),
    "stanford_ai_ethics_philosophy": _env("MODEL_ELITE_STANFORD_AI_ETHICS_PHILOSOPHY", "DeepSeek-V3.2"),
}

# --- Global Elite IV (agents/global_elite_4.py) — 100 сеньоров ---
# Четвёртая волна: чистый технический спецназ — распределённые системы,
# ML/AI глубокого уровня, теоретическая информатика, языки/компиляторы/
# формальные методы, криптография, производительность/железо, data
# engineering, computer vision, физика/матмоделирование, сети. Та же
# логика балансировки по тем же 12 моделям, что и в Global Elite I/II/III.
GLOBAL_ELITE_4_MODEL_ASSIGNMENTS = {
    "princeton_consensus_paxos": _env("MODEL_ELITE_PRINCETON_CONSENSUS_PAXOS", "gpt-5.4"),
    "mit_newsql_spanner": _env("MODEL_ELITE_MIT_NEWSQL_SPANNER", "DeepSeek-V4-Flash"),
    "cmu_timeseries_kernel": _env("MODEL_ELITE_CMU_TIMESERIES_KERNEL", "DeepSeek-V4-Pro"),
    "waterloo_graph_engine": _env("MODEL_ELITE_WATERLOO_GRAPH_ENGINE", "DeepSeek-V3.2"),
    "ucl_event_sourcing_lead": _env("MODEL_ELITE_UCL_EVENT_SOURCING_LEAD", "DeepSeek-V3.2-Speciale"),
    "berkeley_query_optimizer": _env("MODEL_ELITE_BERKELEY_QUERY_OPTIMIZER", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "stanford_rocksdb_kv": _env("MODEL_ELITE_STANFORD_ROCKSDB_KV", "Mistral-Large-3"),
    "eth_replication_consistency": _env("MODEL_ELITE_ETH_REPLICATION_CONSISTENCY", "grok-4.3"),
    "tsinghua_sharding_wechat": _env("MODEL_ELITE_TSINGHUA_SHARDING_WECHAT", "grok-4-20-reasoning"),
    "toronto_redis_inmemory": _env("MODEL_ELITE_TORONTO_REDIS_INMEMORY", "grok-4-20-non-reasoning"),
    "stanford_fewshot_metalearning": _env("MODEL_ELITE_STANFORD_FEWSHOT_METALEARNING", "Kimi-K2.5"),
    "maxplanck_causal_representation": _env("MODEL_ELITE_MAXPLANCK_CAUSAL_REPRESENTATION", "gpt-5.3-codex"),
    "cambridge_bayesian_deep_learning": _env("MODEL_ELITE_CAMBRIDGE_BAYESIAN_DEEP_LEARNING", "gpt-5.4"),
    "cmu_nas_automl": _env("MODEL_ELITE_CMU_NAS_AUTOML", "DeepSeek-V4-Flash"),
    "berkeley_rl_workflow": _env("MODEL_ELITE_BERKELEY_RL_WORKFLOW", "DeepSeek-V4-Pro"),
    "maryland_adversarial_nlp": _env("MODEL_ELITE_MARYLAND_ADVERSARIAL_NLP", "DeepSeek-V3.2"),
    "utokyo_info_geometry": _env("MODEL_ELITE_UTOKYO_INFO_GEOMETRY", "DeepSeek-V3.2-Speciale"),
    "helsinki_federated_privacy": _env("MODEL_ELITE_HELSINKI_FEDERATED_PRIVACY", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "mit_tinyml_ondevice": _env("MODEL_ELITE_MIT_TINYML_ONDEVICE", "Mistral-Large-3"),
    "uw_ml_interpretability": _env("MODEL_ELITE_UW_ML_INTERPRETABILITY", "grok-4.3"),
    "bonn_approximation_algorithms": _env("MODEL_ELITE_BONN_APPROXIMATION_ALGORITHMS", "grok-4-20-reasoning"),
    "technion_online_algorithms": _env("MODEL_ELITE_TECHNION_ONLINE_ALGORITHMS", "grok-4-20-non-reasoning"),
    "rice_streaming_sketching": _env("MODEL_ELITE_RICE_STREAMING_SKETCHING", "Kimi-K2.5"),
    "harvard_algo_game_theory": _env("MODEL_ELITE_HARVARD_ALGO_GAME_THEORY", "gpt-5.3-codex"),
    "waterloo_quantum_algorithms": _env("MODEL_ELITE_WATERLOO_QUANTUM_ALGORITHMS", "gpt-5.4"),
    "mit_finegrained_complexity": _env("MODEL_ELITE_MIT_FINEGRAINED_COMPLEXITY", "DeepSeek-V4-Flash"),
    "grenoble_combinatorial_opt": _env("MODEL_ELITE_GRENOBLE_COMBINATORIAL_OPT", "DeepSeek-V4-Pro"),
    "uw_randomized_algorithms": _env("MODEL_ELITE_UW_RANDOMIZED_ALGORITHMS", "DeepSeek-V3.2"),
    "amsterdam_kolmogorov_complexity": _env("MODEL_ELITE_AMSTERDAM_KOLMOGOROV_COMPLEXITY", "DeepSeek-V3.2-Speciale"),
    "bergen_parameterized_complexity": _env("MODEL_ELITE_BERGEN_PARAMETERIZED_COMPLEXITY", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "edinburgh_dsl_compiler": _env("MODEL_ELITE_EDINBURGH_DSL_COMPILER", "Mistral-Large-3"),
    "oraclelabs_jit_graalvm": _env("MODEL_ELITE_ORACLELABS_JIT_GRAALVM", "grok-4.3"),
    "oxford_static_analysis": _env("MODEL_ELITE_OXFORD_STATIC_ANALYSIS", "grok-4-20-reasoning"),
    "mit_program_synthesis": _env("MODEL_ELITE_MIT_PROGRAM_SYNTHESIS", "grok-4-20-non-reasoning"),
    "inria_coq_dependent_types": _env("MODEL_ELITE_INRIA_COQ_DEPENDENT_TYPES", "Kimi-K2.5"),
    "apple_llvm_backend": _env("MODEL_ELITE_APPLE_LLVM_BACKEND", "gpt-5.3-codex"),
    "uppsala_gc_memory": _env("MODEL_ELITE_UPPSALA_GC_MEMORY", "gpt-5.4"),
    "cambridge_async_concurrency": _env("MODEL_ELITE_CAMBRIDGE_ASYNC_CONCURRENCY", "DeepSeek-V4-Flash"),
    "ucsd_wasm_sandboxing": _env("MODEL_ELITE_UCSD_WASM_SANDBOXING", "DeepSeek-V4-Pro"),
    "stanford_hw_accelerator_compiler": _env("MODEL_ELITE_STANFORD_HW_ACCELERATOR_COMPILER", "DeepSeek-V3.2"),
    "eindhoven_postquantum_crypto": _env("MODEL_ELITE_EINDHOVEN_POSTQUANTUM_CRYPTO", "DeepSeek-V3.2-Speciale"),
    "ibm_homomorphic_encryption": _env("MODEL_ELITE_IBM_HOMOMORPHIC_ENCRYPTION", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "aarhus_mpc_specialist": _env("MODEL_ELITE_AARHUS_MPC_SPECIALIST", "Mistral-Large-3"),
    "berkeley_zk_proofs": _env("MODEL_ELITE_BERKELEY_ZK_PROOFS", "grok-4.3"),
    "cambridge_sidechannel_mitigation": _env("MODEL_ELITE_CAMBRIDGE_SIDECHANNEL_MITIGATION", "grok-4-20-reasoning"),
    "eth_smartcontract_security": _env("MODEL_ELITE_ETH_SMARTCONTRACT_SECURITY", "grok-4-20-non-reasoning"),
    "bologna_liveness_detection": _env("MODEL_ELITE_BOLOGNA_LIVENESS_DETECTION", "Kimi-K2.5"),
    "toronto_pml_architect": _env("MODEL_ELITE_TORONTO_PML_ARCHITECT", "gpt-5.3-codex"),
    "nyu_sbom_security": _env("MODEL_ELITE_NYU_SBOM_SECURITY", "gpt-5.4"),
    "luxembourg_hsm_keymgmt": _env("MODEL_ELITE_LUXEMBOURG_HSM_KEYMGMT", "DeepSeek-V4-Flash"),
    "janestreet_lowlatency_hft": _env("MODEL_ELITE_JANESTREET_LOWLATENCY_HFT", "DeepSeek-V4-Pro"),
    "nvidia_cuda_optimization": _env("MODEL_ELITE_NVIDIA_CUDA_OPTIMIZATION", "DeepSeek-V3.2"),
    "intel_simd_vectorization": _env("MODEL_ELITE_INTEL_SIMD_VECTORIZATION", "DeepSeek-V3.2-Speciale"),
    "eth_rdma_kernel_bypass": _env("MODEL_ELITE_ETH_RDMA_KERNEL_BYPASS", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "waterloo_rtos_qnx": _env("MODEL_ELITE_WATERLOO_RTOS_QNX", "Mistral-Large-3"),
    "xilinx_fpga_ml_inference": _env("MODEL_ELITE_XILINX_FPGA_ML_INFERENCE", "grok-4.3"),
    "arm_power_thermal": _env("MODEL_ELITE_ARM_POWER_THERMAL", "grok-4-20-reasoning"),
    "broadcom_asic_design": _env("MODEL_ELITE_BROADCOM_ASIC_DESIGN", "grok-4-20-non-reasoning"),
    "google_pgo_tuning": _env("MODEL_ELITE_GOOGLE_PGO_TUNING", "Kimi-K2.5"),
    "msr_cache_oblivious": _env("MODEL_ELITE_MSR_CACHE_OBLIVIOUS", "gpt-5.3-codex"),
    "confluent_stream_windowing": _env("MODEL_ELITE_CONFLUENT_STREAM_WINDOWING", "gpt-5.4"),
    "databricks_data_lineage": _env("MODEL_ELITE_DATABRICKS_DATA_LINEAGE", "DeepSeek-V4-Flash"),
    "airbnb_etl_performance": _env("MODEL_ELITE_AIRBNB_ETL_PERFORMANCE", "DeepSeek-V4-Pro"),
    "netflix_lakehouse_iceberg": _env("MODEL_ELITE_NETFLIX_LAKEHOUSE_ICEBERG", "DeepSeek-V3.2"),
    "uber_feature_store": _env("MODEL_ELITE_UBER_FEATURE_STORE", "DeepSeek-V3.2-Speciale"),
    "influxdb_iot_timeseries": _env("MODEL_ELITE_INFLUXDB_IOT_TIMESERIES", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "lyft_data_catalog": _env("MODEL_ELITE_LYFT_DATA_CATALOG", "Mistral-Large-3"),
    "clickhouse_realtime_olap": _env("MODEL_ELITE_CLICKHOUSE_REALTIME_OLAP", "grok-4.3"),
    "debezium_cdc_replication": _env("MODEL_ELITE_DEBEZIUM_CDC_REPLICATION", "grok-4-20-reasoning"),
    "zalando_federated_governance": _env("MODEL_ELITE_ZALANDO_FEDERATED_GOVERNANCE", "grok-4-20-non-reasoning"),
    "eth_sfm_photogrammetry": _env("MODEL_ELITE_ETH_SFM_PHOTOGRAMMETRY", "Kimi-K2.5"),
    "ibm_defect_localization": _env("MODEL_ELITE_IBM_DEFECT_LOCALIZATION", "gpt-5.3-codex"),
    "abbyy_ocr_handwriting": _env("MODEL_ELITE_ABBYY_OCR_HANDWRITING", "gpt-5.4"),
    "netflix_video_compression": _env("MODEL_ELITE_NETFLIX_VIDEO_COMPRESSION", "DeepSeek-V4-Flash"),
    "stanford_3d_bim_alignment": _env("MODEL_ELITE_STANFORD_3D_BIM_ALIGNMENT", "DeepSeek-V4-Pro"),
    "oxford_slam_ar": _env("MODEL_ELITE_OXFORD_SLAM_AR", "DeepSeek-V3.2"),
    "pku_doc_layout_extraction": _env("MODEL_ELITE_PKU_DOC_LAYOUT_EXTRACTION", "DeepSeek-V3.2-Speciale"),
    "linkoping_thermal_analysis": _env("MODEL_ELITE_LINKOPING_THERMAL_ANALYSIS", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "cuhk_video_anomaly": _env("MODEL_ELITE_CUHK_VIDEO_ANOMALY", "Mistral-Large-3"),
    "berkeley_nerf_rendering": _env("MODEL_ELITE_BERKELEY_NERF_RENDERING", "grok-4.3"),
    "tumunich_fem_structural": _env("MODEL_ELITE_TUMUNICH_FEM_STRUCTURAL", "grok-4-20-reasoning"),
    "imperial_cfd_hvac": _env("MODEL_ELITE_IMPERIAL_CFD_HVAC", "grok-4-20-non-reasoning"),
    "utaustin_bayesian_inverse": _env("MODEL_ELITE_UTAUSTIN_BAYESIAN_INVERSE", "Kimi-K2.5"),
    "eth_multiphysics_digitaltwin": _env("MODEL_ELITE_ETH_MULTIPHYSICS_DIGITALTWIN", "gpt-5.3-codex"),
    "oxford_sde_randomfields": _env("MODEL_ELITE_OXFORD_SDE_RANDOMFIELDS", "gpt-5.4"),
    "dtu_topology_optimization": _env("MODEL_ELITE_DTU_TOPOLOGY_OPTIMIZATION", "DeepSeek-V4-Flash"),
    "southampton_acoustic_vibration": _env("MODEL_ELITE_SOUTHAMPTON_ACOUSTIC_VIBRATION", "DeepSeek-V4-Pro"),
    "ucl_daylight_simulation": _env("MODEL_ELITE_UCL_DAYLIGHT_SIMULATION", "DeepSeek-V3.2"),
    "mit_material_degradation": _env("MODEL_ELITE_MIT_MATERIAL_DEGRADATION", "DeepSeek-V3.2-Speciale"),
    "columbia_catastrophe_modeling": _env("MODEL_ELITE_COLUMBIA_CATASTROPHE_MODELING", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "google_quic_protocol": _env("MODEL_ELITE_GOOGLE_QUIC_PROTOCOL", "Mistral-Large-3"),
    "berkeley_mesh_networking": _env("MODEL_ELITE_BERKELEY_MESH_NETWORKING", "grok-4.3"),
    "mit_bbr_congestion": _env("MODEL_ELITE_MIT_BBR_CONGESTION", "grok-4-20-reasoning"),
    "samsung_5g_edge": _env("MODEL_ELITE_SAMSUNG_5G_EDGE", "grok-4-20-non-reasoning"),
    "apple_ble_location": _env("MODEL_ELITE_APPLE_BLE_LOCATION", "Kimi-K2.5"),
    "spacex_starlink_connectivity": _env("MODEL_ELITE_SPACEX_STARLINK_CONNECTIVITY", "gpt-5.3-codex"),
    "paloalto_dpi_security": _env("MODEL_ELITE_PALOALTO_DPI_SECURITY", "gpt-5.4"),
    "facebook_grpc_performance": _env("MODEL_ELITE_FACEBOOK_GRPC_PERFORMANCE", "DeepSeek-V4-Flash"),
    "cern_ptp_timesync": _env("MODEL_ELITE_CERN_PTP_TIMESYNC", "DeepSeek-V4-Pro"),
    "cloudflare_anycast_lb": _env("MODEL_ELITE_CLOUDFLARE_ANYCAST_LB", "DeepSeek-V3.2"),
}

# --- Global Elite V (agents/global_elite_5.py) — 100 сеньоров ---
# Пятая волна: РЕАЛИЗАТОРЫ — Staff/Principal Engineers по технологическим
# стекам (backend, frontend/mobile, DevOps/SRE, security, data/ML
# engineering, embedded/IoT, QA, full-stack), доводящие замысел волн I-IV
# до продакшен-кода. Та же логика балансировки по тем же 12 моделям.
GLOBAL_ELITE_5_MODEL_ASSIGNMENTS = {
    "waterloo_go_staff_backend": _env("MODEL_ELITE_WATERLOO_GO_STAFF_BACKEND", "gpt-5.4"),
    "cambridge_java_payments": _env("MODEL_ELITE_CAMBRIDGE_JAVA_PAYMENTS", "DeepSeek-V4-Flash"),
    "mipt_cpp_rust_systems": _env("MODEL_ELITE_MIPT_CPP_RUST_SYSTEMS", "DeepSeek-V4-Pro"),
    "sydney_python_async": _env("MODEL_ELITE_SYDNEY_PYTHON_ASYNC", "DeepSeek-V3.2"),
    "mit_consul_distributed_impl": _env("MODEL_ELITE_MIT_CONSUL_DISTRIBUTED_IMPL", "DeepSeek-V3.2-Speciale"),
    "epfl_scala_akka": _env("MODEL_ELITE_EPFL_SCALA_AKKA", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "telaviv_nodejs_perf": _env("MODEL_ELITE_TELAVIV_NODEJS_PERF", "Mistral-Large-3"),
    "saopaulo_elixir_otp": _env("MODEL_ELITE_SAOPAULO_ELIXIR_OTP", "grok-4.3"),
    "stanford_oauth_identity_impl": _env("MODEL_ELITE_STANFORD_OAUTH_IDENTITY_IMPL", "grok-4-20-reasoning"),
    "cmu_postgres_internals": _env("MODEL_ELITE_CMU_POSTGRES_INTERNALS", "grok-4-20-non-reasoning"),
    "toronto_stripe_api": _env("MODEL_ELITE_TORONTO_STRIPE_API", "Kimi-K2.5"),
    "ubc_microservices_decomposer": _env("MODEL_ELITE_UBC_MICROSERVICES_DECOMPOSER", "gpt-5.3-codex"),
    "aalto_kafka_eventbus": _env("MODEL_ELITE_AALTO_KAFKA_EVENTBUS", "gpt-5.4"),
    "waterloo_graphql_backend": _env("MODEL_ELITE_WATERLOO_GRAPHQL_BACKEND", "DeepSeek-V4-Flash"),
    "uiuc_grpc_protobuf": _env("MODEL_ELITE_UIUC_GRPC_PROTOBUF", "DeepSeek-V4-Pro"),
    "edinburgh_legacy_modernization": _env("MODEL_ELITE_EDINBURGH_LEGACY_MODERNIZATION", "DeepSeek-V3.2"),
    "helsinki_bff_specialist": _env("MODEL_ELITE_HELSINKI_BFF_SPECIALIST", "DeepSeek-V3.2-Speciale"),
    "patras_distributed_caching": _env("MODEL_ELITE_PATRAS_DISTRIBUTED_CACHING", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "pku_rocketmq_broker": _env("MODEL_ELITE_PKU_ROCKETMQ_BROKER", "Mistral-Large-3"),
    "lugano_saga_workflow": _env("MODEL_ELITE_LUGANO_SAGA_WORKFLOW", "grok-4.3"),
    "artcenter_react_designsystem": _env("MODEL_ELITE_ARTCENTER_REACT_DESIGNSYSTEM", "grok-4-20-reasoning"),
    "usc_reactnative_lead": _env("MODEL_ELITE_USC_REACTNATIVE_LEAD", "grok-4-20-non-reasoning"),
    "bologna_swiftui_ios": _env("MODEL_ELITE_BOLOGNA_SWIFTUI_IOS", "Kimi-K2.5"),
    "iitbombay_android_perf": _env("MODEL_ELITE_IITBOMBAY_ANDROID_PERF", "gpt-5.3-codex"),
    "tsinghua_flutter_lark": _env("MODEL_ELITE_TSINGHUA_FLUTTER_LARK", "gpt-5.4"),
    "michigan_jest_frontend_qa": _env("MODEL_ELITE_MICHIGAN_JEST_FRONTEND_QA", "DeepSeek-V4-Flash"),
    "eth_webgl_bim_viz": _env("MODEL_ELITE_ETH_WEBGL_BIM_VIZ", "DeepSeek-V4-Pro"),
    "google_pwa_devrel": _env("MODEL_ELITE_GOOGLE_PWA_DEVREL", "DeepSeek-V3.2"),
    "utaustin_wcag_impl": _env("MODEL_ELITE_UTAUSTIN_WCAG_IMPL", "DeepSeek-V3.2-Speciale"),
    "mitmedialab_ui_animation": _env("MODEL_ELITE_MITMEDIALAB_UI_ANIMATION", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "utokyo_css_designsystem": _env("MODEL_ELITE_UTOKYO_CSS_DESIGNSYSTEM", "Mistral-Large-3"),
    "technion_mobile_security_impl": _env("MODEL_ELITE_TECHNION_MOBILE_SECURITY_IMPL", "grok-4.3"),
    "twente_electron_desktop": _env("MODEL_ELITE_TWENTE_ELECTRON_DESKTOP", "grok-4-20-reasoning"),
    "sydney_crdt_collab": _env("MODEL_ELITE_SYDNEY_CRDT_COLLAB", "grok-4-20-non-reasoning"),
    "kaist_wearable_companion": _env("MODEL_ELITE_KAIST_WEARABLE_COMPANION", "Kimi-K2.5"),
    "google_gke_platform": _env("MODEL_ELITE_GOOGLE_GKE_PLATFORM", "gpt-5.3-codex"),
    "hashicorp_terraform_iac": _env("MODEL_ELITE_HASHICORP_TERRAFORM_IAC", "gpt-5.4"),
    "github_actions_cicd": _env("MODEL_ELITE_GITHUB_ACTIONS_CICD", "DeepSeek-V4-Flash"),
    "google_sre_borg_incident": _env("MODEL_ELITE_GOOGLE_SRE_BORG_INCIDENT", "DeepSeek-V4-Pro"),
    "grafana_lgtm_observability": _env("MODEL_ELITE_GRAFANA_LGTM_OBSERVABILITY", "DeepSeek-V3.2"),
    "hashicorp_vault_secrets": _env("MODEL_ELITE_HASHICORP_VAULT_SECRETS", "DeepSeek-V3.2-Speciale"),
    "aws_finops_lead": _env("MODEL_ELITE_AWS_FINOPS_LEAD", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "crunchydata_postgres_dre": _env("MODEL_ELITE_CRUNCHYDATA_POSTGRES_DRE", "Mistral-Large-3"),
    "cloudflare_cdn_edge": _env("MODEL_ELITE_CLOUDFLARE_CDN_EDGE", "grok-4.3"),
    "aqua_container_hardening": _env("MODEL_ELITE_AQUA_CONTAINER_HARDENING", "grok-4-20-reasoning"),
    "gremlin_infra_chaos_impl": _env("MODEL_ELITE_GREMLIN_INFRA_CHAOS_IMPL", "grok-4-20-non-reasoning"),
    "tetrate_servicemesh_operator": _env("MODEL_ELITE_TETRATE_SERVICEMESH_OPERATOR", "Kimi-K2.5"),
    "veeam_dr_architect_impl": _env("MODEL_ELITE_VEEAM_DR_ARCHITECT_IMPL", "gpt-5.3-codex"),
    "letsencrypt_pki_automation": _env("MODEL_ELITE_LETSENCRYPT_PKI_AUTOMATION", "gpt-5.4"),
    "bosch_iot_fleet_ota": _env("MODEL_ELITE_BOSCH_IOT_FLEET_OTA", "DeepSeek-V4-Flash"),
    "msrc_appsec_sdlc": _env("MODEL_ELITE_MSRC_APPSEC_SDLC", "DeepSeek-V4-Pro"),
    "bishopfox_redteam_impl": _env("MODEL_ELITE_BISHOPFOX_REDTEAM_IMPL", "DeepSeek-V3.2"),
    "google_tink_crypto_impl": _env("MODEL_ELITE_GOOGLE_TINK_CRYPTO_IMPL", "DeepSeek-V3.2-Speciale"),
    "auth0_iam_rbac_impl": _env("MODEL_ELITE_AUTH0_IAM_RBAC_IMPL", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "symantec_dlp_specialist": _env("MODEL_ELITE_SYMANTEC_DLP_SPECIALIST", "Mistral-Large-3"),
    "visa_fraud_rules_impl": _env("MODEL_ELITE_VISA_FRAUD_RULES_IMPL", "grok-4.3"),
    "splunk_siem_correlation_impl": _env("MODEL_ELITE_SPLUNK_SIEM_CORRELATION_IMPL", "grok-4-20-reasoning"),
    "snyk_dependency_scanner_impl": _env("MODEL_ELITE_SNYK_DEPENDENCY_SCANNER_IMPL", "grok-4-20-non-reasoning"),
    "coverity_secure_codereview": _env("MODEL_ELITE_COVERITY_SECURE_CODEREVIEW", "Kimi-K2.5"),
    "thales_hsm_root_of_trust": _env("MODEL_ELITE_THALES_HSM_ROOT_OF_TRUST", "gpt-5.3-codex"),
    "databricks_spark_etl_impl": _env("MODEL_ELITE_DATABRICKS_SPARK_ETL_IMPL", "gpt-5.4"),
    "ververica_flink_streaming": _env("MODEL_ELITE_VERVERICA_FLINK_STREAMING", "DeepSeek-V4-Flash"),
    "tecton_feature_store_impl": _env("MODEL_ELITE_TECTON_FEATURE_STORE_IMPL", "DeepSeek-V4-Pro"),
    "googleai_kubeflow_argo": _env("MODEL_ELITE_GOOGLEAI_KUBEFLOW_ARGO", "DeepSeek-V3.2"),
    "nvidia_triton_serving": _env("MODEL_ELITE_NVIDIA_TRITON_SERVING", "DeepSeek-V3.2-Speciale"),
    "greatexpectations_dataquality": _env("MODEL_ELITE_GREATEXPECTATIONS_DATAQUALITY", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "snowflake_dwh_architect_impl": _env("MODEL_ELITE_SNOWFLAKE_DWH_ARCHITECT_IMPL", "Mistral-Large-3"),
    "dbtlabs_analytics_eng": _env("MODEL_ELITE_DBTLABS_ANALYTICS_ENG", "grok-4.3"),
    "pinecone_vectordb_impl": _env("MODEL_ELITE_PINECONE_VECTORDB_IMPL", "grok-4-20-reasoning"),
    "linkedin_datahub_catalog_impl": _env("MODEL_ELITE_LINKEDIN_DATAHUB_CATALOG_IMPL", "grok-4-20-non-reasoning"),
    "arize_ml_drift_monitoring": _env("MODEL_ELITE_ARIZE_ML_DRIFT_MONITORING", "Kimi-K2.5"),
    "scaleai_labeling_pipeline": _env("MODEL_ELITE_SCALEAI_LABELING_PIPELINE", "gpt-5.3-codex"),
    "optimizely_experimentation_impl": _env("MODEL_ELITE_OPTIMIZELY_EXPERIMENTATION_IMPL", "gpt-5.4"),
    "privitar_privacy_eng_impl": _env("MODEL_ELITE_PRIVITAR_PRIVACY_ENG_IMPL", "DeepSeek-V4-Flash"),
    "neo4j_graph_data_eng_impl": _env("MODEL_ELITE_NEO4J_GRAPH_DATA_ENG_IMPL", "DeepSeek-V4-Pro"),
    "cambridge_freertos_firmware": _env("MODEL_ELITE_CAMBRIDGE_FREERTOS_FIRMWARE", "DeepSeek-V3.2"),
    "ti_yocto_embeddedlinux": _env("MODEL_ELITE_TI_YOCTO_EMBEDDEDLINUX", "DeepSeek-V3.2-Speciale"),
    "siliconlabs_ble_zigbee_lora": _env("MODEL_ELITE_SILICONLABS_BLE_ZIGBEE_LORA", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "siemens_plc_scada": _env("MODEL_ELITE_SIEMENS_PLC_SCADA", "Mistral-Large-3"),
    "nvidia_jetson_edge_cv": _env("MODEL_ELITE_NVIDIA_JETSON_EDGE_CV", "grok-4.3"),
    "nordic_power_battery_mgmt": _env("MODEL_ELITE_NORDIC_POWER_BATTERY_MGMT", "grok-4-20-reasoning"),
    "bosch_sensortec_drivers": _env("MODEL_ELITE_BOSCH_SENSORTEC_DRIVERS", "grok-4-20-non-reasoning"),
    "qnx_safety_critical_impl": _env("MODEL_ELITE_QNX_SAFETY_CRITICAL_IMPL", "Kimi-K2.5"),
    "analogdevices_dsp_impl": _env("MODEL_ELITE_ANALOGDEVICES_DSP_IMPL", "gpt-5.3-codex"),
    "dspace_hil_testing": _env("MODEL_ELITE_DSPACE_HIL_TESTING", "gpt-5.4"),
    "booking_pytest_test_architect": _env("MODEL_ELITE_BOOKING_PYTEST_TEST_ARCHITECT", "DeepSeek-V4-Flash"),
    "gatling_load_testing_lead": _env("MODEL_ELITE_GATLING_LOAD_TESTING_LEAD", "DeepSeek-V4-Pro"),
    "veracode_sast_dast_impl": _env("MODEL_ELITE_VERACODE_SAST_DAST_IMPL", "DeepSeek-V3.2"),
    "uber_appium_mobile_testing": _env("MODEL_ELITE_UBER_APPIUM_MOBILE_TESTING", "DeepSeek-V3.2-Speciale"),
    "pactflow_contract_testing": _env("MODEL_ELITE_PACTFLOW_CONTRACT_TESTING", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "chromatic_visual_regression_impl": _env("MODEL_ELITE_CHROMATIC_VISUAL_REGRESSION_IMPL", "Mistral-Large-3"),
    "deque_a11y_test_automation": _env("MODEL_ELITE_DEQUE_A11Y_TEST_AUTOMATION", "grok-4.3"),
    "aws_fis_chaos_testing_impl": _env("MODEL_ELITE_AWS_FIS_CHAOS_TESTING_IMPL", "grok-4-20-reasoning"),
    "deloitte_data_reconciliation": _env("MODEL_ELITE_DELOITTE_DATA_RECONCILIATION", "grok-4-20-non-reasoning"),
    "microsoft_exploratory_tester": _env("MODEL_ELITE_MICROSOFT_EXPLORATORY_TESTER", "Kimi-K2.5"),
    "mit_fullstack_polyglot": _env("MODEL_ELITE_MIT_FULLSTACK_POLYGLOT", "gpt-5.3-codex"),
    "stanford_dschool_prototype_racer": _env("MODEL_ELITE_STANFORD_DSCHOOL_PROTOTYPE_RACER", "gpt-5.4"),
    "google_readability_refactoring": _env("MODEL_ELITE_GOOGLE_READABILITY_REFACTORING", "DeepSeek-V4-Flash"),
    "ibm_integration_migration": _env("MODEL_ELITE_IBM_INTEGRATION_MIGRATION", "DeepSeek-V4-Pro"),
    "spotify_backstage_dx": _env("MODEL_ELITE_SPOTIFY_BACKSTAGE_DX", "DeepSeek-V3.2"),
}


# --- Global Elite VI (agents/global_elite_6.py) --- 100 сеньоров ---
# Шестая волна: универсальные творцы на стыке математики, физики и
# инженерии (теоретики, физики-модельеры, системные архитекторы,
# алгоритмисты, междисциплинарные исследователи). Та же логика
# балансировки по тем же 12 моделям, что и в предыдущих волнах.
GLOBAL_ELITE_6_MODEL_ASSIGNMENTS = {
    "princeton_algebraic_topology": _env("MODEL_ELITE_PRINCETON_ALGEBRAIC_TOPOLOGY", "gpt-5.4"),
    "sorbonne_category_theory": _env("MODEL_ELITE_SORBONNE_CATEGORY_THEORY", "DeepSeek-V4-Flash"),
    "bonn_extreme_value_stats": _env("MODEL_ELITE_BONN_EXTREME_VALUE_STATS", "DeepSeek-V4-Pro"),
    "mit_inverse_problems": _env("MODEL_ELITE_MIT_INVERSE_PROBLEMS", "DeepSeek-V3.2"),
    "grenoble_combinatorial_opt": _env("MODEL_ELITE_GRENOBLE_COMBINATORIAL_OPT", "DeepSeek-V3.2-Speciale"),
    "mit_complexity_theory": _env("MODEL_ELITE_MIT_COMPLEXITY_THEORY", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "pku_riemannian_geometry": _env("MODEL_ELITE_PKU_RIEMANNIAN_GEOMETRY", "Mistral-Large-3"),
    "waterloo_graph_theory": _env("MODEL_ELITE_WATERLOO_GRAPH_THEORY", "grok-4.3"),
    "ens_functional_analysis": _env("MODEL_ELITE_ENS_FUNCTIONAL_ANALYSIS", "grok-4-20-reasoning"),
    "weizmann_pq_crypto": _env("MODEL_ELITE_WEIZMANN_PQ_CRYPTO", "grok-4-20-non-reasoning"),
    "oxford_formal_logic": _env("MODEL_ELITE_OXFORD_FORMAL_LOGIC", "Kimi-K2.5"),
    "south_carolina_approximation_theory": _env("MODEL_ELITE_SOUTH_CAROLINA_APPROXIMATION_THEORY", "gpt-5.3-codex"),
    "eth_stochastic_calculus": _env("MODEL_ELITE_ETH_STOCHASTIC_CALCULUS", "gpt-5.4"),
    "msu_pde_supply_chain": _env("MODEL_ELITE_MSU_PDE_SUPPLY_CHAIN", "DeepSeek-V4-Flash"),
    "amsterdam_information_theory": _env("MODEL_ELITE_AMSTERDAM_INFORMATION_THEORY", "DeepSeek-V4-Pro"),
    "stanford_mechanism_design": _env("MODEL_ELITE_STANFORD_MECHANISM_DESIGN", "DeepSeek-V3.2"),
    "hebrew_discrete_geometry": _env("MODEL_ELITE_HEBREW_DISCRETE_GEOMETRY", "DeepSeek-V3.2-Speciale"),
    "utokyo_numerical_analysis": _env("MODEL_ELITE_UTOKYO_NUMERICAL_ANALYSIS", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "harvard_error_correcting_codes": _env("MODEL_ELITE_HARVARD_ERROR_CORRECTING_CODES", "Mistral-Large-3"),
    "caltech_stat_field_theory": _env("MODEL_ELITE_CALTECH_STAT_FIELD_THEORY", "grok-4.3"),
    "cambridge_many_body_stochastic": _env("MODEL_ELITE_CAMBRIDGE_MANY_BODY_STOCHASTIC", "grok-4-20-reasoning"),
    "imperial_fluid_dynamics": _env("MODEL_ELITE_IMPERIAL_FLUID_DYNAMICS", "grok-4-20-non-reasoning"),
    "cern_rare_event_stats": _env("MODEL_ELITE_CERN_RARE_EVENT_STATS", "Kimi-K2.5"),
    "arizona_photogrammetry_optics": _env("MODEL_ELITE_ARIZONA_PHOTOGRAMMETRY_OPTICS", "gpt-5.3-codex"),
    "princeton_signal_denoising": _env("MODEL_ELITE_PRINCETON_SIGNAL_DENOISING", "gpt-5.4"),
    "eth_material_degradation": _env("MODEL_ELITE_ETH_MATERIAL_DEGRADATION", "DeepSeek-V4-Flash"),
    "rockefeller_evolutionary_biophysics": _env("MODEL_ELITE_ROCKEFELLER_EVOLUTIONARY_BIOPHYSICS", "DeepSeek-V4-Pro"),
    "utokyo_geophysics_vibration": _env("MODEL_ELITE_UTOKYO_GEOPHYSICS_VIBRATION", "DeepSeek-V3.2"),
    "melbourne_climatology_seasonality": _env("MODEL_ELITE_MELBOURNE_CLIMATOLOGY_SEASONALITY", "DeepSeek-V3.2-Speciale"),
    "budker_realtime_beam_control": _env("MODEL_ELITE_BUDKER_REALTIME_BEAM_CONTROL", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "tudelft_turbulence_flow": _env("MODEL_ELITE_TUDELFT_TURBULENCE_FLOW", "Mistral-Large-3"),
    "maxplanck_quantum_correlations": _env("MODEL_ELITE_MAXPLANCK_QUANTUM_CORRELATIONS", "grok-4.3"),
    "caltech_ligo_noise_extraction": _env("MODEL_ELITE_CALTECH_LIGO_NOISE_EXTRACTION", "grok-4-20-reasoning"),
    "southampton_acoustic_mapping": _env("MODEL_ELITE_SOUTHAMPTON_ACOUSTIC_MAPPING", "grok-4-20-non-reasoning"),
    "cambridge_mesh_radiofrequency": _env("MODEL_ELITE_CAMBRIDGE_MESH_RADIOFREQUENCY", "Kimi-K2.5"),
    "mit_thermal_infra_cooling": _env("MODEL_ELITE_MIT_THERMAL_INFRA_COOLING", "gpt-5.3-codex"),
    "oxford_cryogenic_extrapolation": _env("MODEL_ELITE_OXFORD_CRYOGENIC_EXTRAPOLATION", "gpt-5.4"),
    "pnpi_experiment_discipline": _env("MODEL_ELITE_PNPI_EXPERIMENT_DISCIPLINE", "DeepSeek-V4-Flash"),
    "princeton_plasma_collective_behavior": _env("MODEL_ELITE_PRINCETON_PLASMA_COLLECTIVE_BEHAVIOR", "DeepSeek-V4-Pro"),
    "harvard_medical_calibration": _env("MODEL_ELITE_HARVARD_MEDICAL_CALIBRATION", "DeepSeek-V3.2"),
    "jpl_fault_tolerant_architect": _env("MODEL_ELITE_JPL_FAULT_TOLERANT_ARCHITECT", "DeepSeek-V3.2-Speciale"),
    "intel_compute_model_architect": _env("MODEL_ELITE_INTEL_COMPUTE_MODEL_ARCHITECT", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "eth_reliability_bridge_engineer": _env("MODEL_ELITE_ETH_RELIABILITY_BRIDGE_ENGINEER", "Mistral-Large-3"),
    "shell_zero_failure_engineer": _env("MODEL_ELITE_SHELL_ZERO_FAILURE_ENGINEER", "grok-4.3"),
    "ericsson_5g_resilient_comms": _env("MODEL_ELITE_ERICSSON_5G_RESILIENT_COMMS", "grok-4-20-reasoning"),
    "bostondynamics_stabilization_control": _env("MODEL_ELITE_BOSTONDYNAMICS_STABILIZATION_CONTROL", "grok-4-20-non-reasoning"),
    "airbus_certification_engineer": _env("MODEL_ELITE_AIRBUS_CERTIFICATION_ENGINEER", "Kimi-K2.5"),
    "abb_load_balancing_engineer": _env("MODEL_ELITE_ABB_LOAD_BALANCING_ENGINEER", "gpt-5.3-codex"),
    "veolia_pipeline_as_filters": _env("MODEL_ELITE_VEOLIA_PIPELINE_AS_FILTERS", "gpt-5.4"),
    "herrenknecht_uncertainty_pm": _env("MODEL_ELITE_HERRENKNECHT_UNCERTAINTY_PM", "DeepSeek-V4-Flash"),
    "spacex_modular_satellite_architect": _env("MODEL_ELITE_SPACEX_MODULAR_SATELLITE_ARCHITECT", "DeepSeek-V4-Pro"),
    "waymo_sensor_planner_integration": _env("MODEL_ELITE_WAYMO_SENSOR_PLANNER_INTEGRATION", "DeepSeek-V3.2"),
    "iter_realtime_engineer": _env("MODEL_ELITE_ITER_REALTIME_ENGINEER", "DeepSeek-V3.2-Speciale"),
    "google_datacenter_placement_architect": _env("MODEL_ELITE_GOOGLE_DATACENTER_PLACEMENT_ARCHITECT", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "asml_precision_calibration_engineer": _env("MODEL_ELITE_ASML_PRECISION_CALIBRATION_ENGINEER", "Mistral-Large-3"),
    "hydroquebec_longterm_planning_architect": _env("MODEL_ELITE_HYDROQUEBEC_LONGTERM_PLANNING_ARCHITECT", "grok-4.3"),
    "som_load_bearing_engineer": _env("MODEL_ELITE_SOM_LOAD_BEARING_ENGINEER", "grok-4-20-reasoning"),
    "navalgroup_offline_architect": _env("MODEL_ELITE_NAVALGROUP_OFFLINE_ARCHITECT", "grok-4-20-non-reasoning"),
    "eso_adaptive_optics_filtering": _env("MODEL_ELITE_ESO_ADAPTIVE_OPTICS_FILTERING", "Kimi-K2.5"),
    "roscosmos_checklist_engineer": _env("MODEL_ELITE_ROSCOSMOS_CHECKLIST_ENGINEER", "gpt-5.3-codex"),
    "warsaw_icpc_reference_impl": _env("MODEL_ELITE_WARSAW_ICPC_REFERENCE_IMPL", "gpt-5.4"),
    "janestreet_nanosecond_optimizer": _env("MODEL_ELITE_JANESTREET_NANOSECOND_OPTIMIZER", "DeepSeek-V4-Flash"),
    "apple_jit_compiler_engineer": _env("MODEL_ELITE_APPLE_JIT_COMPILER_ENGINEER", "DeepSeek-V4-Pro"),
    "google_search_ranking_engineer": _env("MODEL_ELITE_GOOGLE_SEARCH_RANKING_ENGINEER", "DeepSeek-V3.2"),
    "snowflake_petabyte_analytics_engineer": _env("MODEL_ELITE_SNOWFLAKE_PETABYTE_ANALYTICS_ENGINEER", "DeepSeek-V3.2-Speciale"),
    "epicgames_complexity_visualization": _env("MODEL_ELITE_EPICGAMES_COMPLEXITY_VISUALIZATION", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "signal_e2e_crypto_engineer": _env("MODEL_ELITE_SIGNAL_E2E_CRYPTO_ENGINEER", "Mistral-Large-3"),
    "netflix_log_compression_engineer": _env("MODEL_ELITE_NETFLIX_LOG_COMPRESSION_ENGINEER", "grok-4.3"),
    "cern_lossless_streaming_engineer": _env("MODEL_ELITE_CERN_LOSSLESS_STREAMING_ENGINEER", "grok-4-20-reasoning"),
    "msr_os_kernel_optimizer": _env("MODEL_ELITE_MSR_OS_KERNEL_OPTIMIZER", "grok-4-20-non-reasoning"),
    "ethereum_consensus_engineer": _env("MODEL_ELITE_ETHEREUM_CONSENSUS_ENGINEER", "Kimi-K2.5"),
    "autodesk_cad_geometry_engineer": _env("MODEL_ELITE_AUTODESK_CAD_GEOMETRY_ENGINEER", "gpt-5.3-codex"),
    "xilinx_fpga_inference_engineer": _env("MODEL_ELITE_XILINX_FPGA_INFERENCE_ENGINEER", "gpt-5.4"),
    "amazon_alexa_voice_engineer": _env("MODEL_ELITE_AMAZON_ALEXA_VOICE_ENGINEER", "DeepSeek-V4-Flash"),
    "netflix_recsys_risk_predictor": _env("MODEL_ELITE_NETFLIX_RECSYS_RISK_PREDICTOR", "DeepSeek-V4-Pro"),
    "inria_formal_verification_engineer": _env("MODEL_ELITE_INRIA_FORMAL_VERIFICATION_ENGINEER", "DeepSeek-V3.2"),
    "nvidia_physx_material_engineer": _env("MODEL_ELITE_NVIDIA_PHYSX_MATERIAL_ENGINEER", "DeepSeek-V3.2-Speciale"),
    "qualcomm_signal_processing_engineer": _env("MODEL_ELITE_QUALCOMM_SIGNAL_PROCESSING_ENGINEER", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "broad_bioinformatics_sequence_engineer": _env("MODEL_ELITE_BROAD_BIOINFORMATICS_SEQUENCE_ENGINEER", "Mistral-Large-3"),
    "ceph_exabyte_storage_engineer": _env("MODEL_ELITE_CEPH_EXABYTE_STORAGE_ENGINEER", "grok-4.3"),
    "ucl_neural_ensemble_ai": _env("MODEL_ELITE_UCL_NEURAL_ENSEMBLE_AI", "grok-4-20-reasoning"),
    "stanford_construction_ontology_linguist": _env("MODEL_ELITE_STANFORD_CONSTRUCTION_ONTOLOGY_LINGUIST", "grok-4-20-non-reasoning"),
    "mit_internal_resource_economist": _env("MODEL_ELITE_MIT_INTERNAL_RESOURCE_ECONOMIST", "Kimi-K2.5"),
    "harvard_genetic_algorithm_biologist": _env("MODEL_ELITE_HARVARD_GENETIC_ALGORITHM_BIOLOGIST", "gpt-5.3-codex"),
    "york_dashboard_perception_psychologist": _env("MODEL_ELITE_YORK_DASHBOARD_PERCEPTION_PSYCHOLOGIST", "gpt-5.4"),
    "ircam_harmonic_pattern_analyst": _env("MODEL_ELITE_IRCAM_HARMONIC_PATTERN_ANALYST", "DeepSeek-V4-Flash"),
    "zahahadid_generative_structure_architect": _env("MODEL_ELITE_ZAHAHADID_GENERATIVE_STRUCTURE_ARCHITECT", "DeepSeek-V4-Pro"),
    "shell_geology_ml_explorer": _env("MODEL_ELITE_SHELL_GEOLOGY_ML_EXPLORER", "DeepSeek-V3.2"),
    "hopkins_ab_testing_biostatistician": _env("MODEL_ELITE_HOPKINS_AB_TESTING_BIOSTATISTICIAN", "DeepSeek-V3.2-Speciale"),
    "harvard_regulatory_logic_lawyer": _env("MODEL_ELITE_HARVARD_REGULATORY_LOGIC_LAWYER", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "columbia_network_sociologist": _env("MODEL_ELITE_COLUMBIA_NETWORK_SOCIOLOGIST", "Mistral-Large-3"),
    "chicago_hci_anthropologist": _env("MODEL_ELITE_CHICAGO_HCI_ANTHROPOLOGIST", "grok-4.3"),
    "ecmwf_weather_impact_meteorologist": _env("MODEL_ELITE_ECMWF_WEATHER_IMPACT_METEOROLOGIST", "grok-4-20-reasoning"),
    "ubc_sensor_network_ecologist": _env("MODEL_ELITE_UBC_SENSOR_NETWORK_ECOLOGIST", "grok-4-20-non-reasoning"),
    "esri_gis_geographer": _env("MODEL_ELITE_ESRI_GIS_GEOGRAPHER", "Kimi-K2.5"),
    "oxford_ai_alignment_philosopher": _env("MODEL_ELITE_OXFORD_AI_ALIGNMENT_PHILOSOPHER", "gpt-5.3-codex"),
    "mit_tech_displacement_historian": _env("MODEL_ELITE_MIT_TECH_DISPLACEMENT_HISTORIAN", "gpt-5.4"),
    "florence_quality_pattern_art_historian": _env("MODEL_ELITE_FLORENCE_QUALITY_PATTERN_ART_HISTORIAN", "DeepSeek-V4-Flash"),
    "barcelona_tactical_sports_analyst": _env("MODEL_ELITE_BARCELONA_TACTICAL_SPORTS_ANALYST", "DeepSeek-V4-Pro"),
    "elbulli_precise_process_automation": _env("MODEL_ELITE_ELBULLI_PRECISE_PROCESS_AUTOMATION", "DeepSeek-V3.2"),
}
