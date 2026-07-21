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
grok-4-20-reasoning/non-reasoning, Kimi-K2.7-Code/K2.5, gpt-5.3-codex)
активно используются во многих ролях — то есть проблема выше либо была
решена, либо затрагивала не все сценарии. Если 500-е ошибки периодически
всплывают — скорее всего именно на этих ролях; см. workflows/_common.py:
safe_agent_run() уже ретраит и логирует, кто именно упал, вместо того
чтобы ронять весь workflow. Отдельно: agents/review_gate.py::fuzzer
намеренно на модели не из той же линейки, что пишет код (сейчас
Kimi-K2.7-Code) — цель разнообразие моделей на ревью, а не экономия.

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
                  non-reasoning, Kimi-K2.7-Code/K2.5, gpt-5.3-codex —
                  тоже очень сильные модели, дешевле topового уровня, но
                  с низкой квотой (4 запроса каждая) — используются для
                  read-only/дискуссионных ролей и Review Gate fuzzer'а,
                  размазаны поровну по всем провайдерам, не
                  концентрируются.

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
    "cto": _env("MODEL_CTO", "gpt-5.4"),

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
    # разнообразие моделей, чтобы ловить разные слепые пятна. Kimi-K2.7-Code
    # специализирован именно на коде (в т.ч. тестовом), но это другая
    # архитектура/линейка обучения, чем у пишущей код модели.
    "fuzzer": _env("MODEL_FUZZER", "Kimi-K2.7-Code"),
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
    "itmo": _env("MODEL_ITMO", "Kimi-K2.7-Code"),
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
    "principal_systems_architect": _env("MODEL_FELLOW_SYSTEMS", "Kimi-K2.7-Code"),
    "physics_informed_ml_engineer": _env("MODEL_FELLOW_PHYSICS_ML", "gpt-5.4"),
    "language_compiler_architect": _env("MODEL_FELLOW_COMPILER", "Kimi-K2.7-Code"),
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
# Kimi-K2.7-Code/K2.5, gpt-5.3-codex), нагрузка сбалансирована
# (10-12 на модель), а не концентрируется на одной-двух.
GLOBAL_ELITE_1_MODEL_ASSIGNMENTS = {
    "sjtu_acm": _env("MODEL_ELITE_SJTU_ACM", "DeepSeek-V4-Pro"),
    "zju_cv": _env("MODEL_ELITE_ZJU_CV", "gpt-5.4"),
    "fudan_nlp": _env("MODEL_ELITE_FUDAN_NLP", "DeepSeek-V4-Flash"),
    "cas_amss_math": _env("MODEL_ELITE_CAS_AMSS_MATH", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "ustc_speech": _env("MODEL_ELITE_USTC_SPEECH", "grok-4-20-non-reasoning"),
    "nudt_algo": _env("MODEL_ELITE_NUDT_ALGO", "Kimi-K2.7-Code"),
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
    "fudan_adversarial_ml": _env("MODEL_ELITE_FUDAN_ADVERSARIAL_ML", "Kimi-K2.7-Code"),
    "cas_ict_chips": _env("MODEL_ELITE_CAS_ICT_CHIPS", "Kimi-K2.7-Code"),
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
    "xidian_lowend": _env("MODEL_ELITE_XIDIAN_LOWEND", "Kimi-K2.7-Code"),
    "neu_china_microservices": _env("MODEL_ELITE_NEU_CHINA_MICROSERVICES", "Kimi-K2.7-Code"),
    "sjtu_realtime": _env("MODEL_ELITE_SJTU_REALTIME", "gpt-5.4"),
    "hust_ratelimit": _env("MODEL_ELITE_HUST_RATELIMIT", "Mistral-Large-3"),
    "sysu_privacy": _env("MODEL_ELITE_SYSU_PRIVACY", "Mistral-Large-3"),
    "swjtu_api": _env("MODEL_ELITE_SWJTU_API", "DeepSeek-V4-Pro"),
    "dlut_scheduling": _env("MODEL_ELITE_DLUT_SCHEDULING", "grok-4.3"),
    "tongji_dataviz": _env("MODEL_ELITE_TONGJI_DATAVIZ", "grok-4-20-non-reasoning"),
    "pku_xai": _env("MODEL_ELITE_PKU_XAI", "Kimi-K2.5"),
    "zju_mobile": _env("MODEL_ELITE_ZJU_MOBILE", "Kimi-K2.7-Code"),
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
    "waterloo_clientperf": _env("MODEL_ELITE_WATERLOO_CLIENTPERF", "Kimi-K2.7-Code"),
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
    "polimi_construction": _env("MODEL_ELITE_POLIMI_CONSTRUCTION", "Kimi-K2.7-Code"),
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
    "aub_reconstruction": _env("MODEL_ELITE_AUB_RECONSTRUCTION", "Kimi-K2.7-Code"),
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
    "mipt_networkphysics": _env("MODEL_ELITE_MIPT_NETWORKPHYSICS", "Kimi-K2.7-Code"),
    "itmo_dupdetect": _env("MODEL_ELITE_ITMO_DUPDETECT", "Kimi-K2.5"),
    "nsu_complexityaudit": _env("MODEL_ELITE_NSU_COMPLEXITYAUDIT", "Mistral-Large-3"),
    "spbgu_devtooling": _env("MODEL_ELITE_SPBGU_DEVTOOLING", "gpt-5.3-codex"),
    "hse_demandforecast": _env("MODEL_ELITE_HSE_DEMANDFORECAST", "gpt-5.4"),
    "bsu_minsk_engagement": _env("MODEL_ELITE_BSU_MINSK_ENGAGEMENT", "DeepSeek-V4-Flash"),
    "kazan_codeswitching": _env("MODEL_ELITE_KAZAN_CODESWITCHING", "DeepSeek-V4-Pro"),
    "ural_b2bcompliance": _env("MODEL_ELITE_URAL_B2BCOMPLIANCE", "DeepSeek-V3.2-Speciale"),
    "tomsk_predictivemaintenance": _env("MODEL_ELITE_TOMSK_PREDICTIVEMAINTENANCE", "Kimi-K2.7-Code"),
}
