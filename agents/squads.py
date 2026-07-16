"""
Инженерные отряды — постоянные команды (не ad-hoc подбор под задачу), в
отличие от одиночного лид-инженера (agents/engineering.py), который
по-прежнему существует для простых одиночных задач (main_engineering.py).

Смысл: раньше при росте ростера до 25+ человек большинство людей почти
не участвовали в реальной работе с кодом — только лид-инженер что-то
писал, изредка призывая 1-2 специалистов. Теперь есть 2 постоянных
отряда, которые работают ПАРАЛЛЕЛЬНО над РАЗНЫМИ задачами — это и
задействует простаивающих специалистов, и создаёт больше "рабочих
мест", как просил Валик.

Отряд Альфа "Ядро и данные" — фокус на backend-архитектуре, БД,
производительности. Состав: Squad Lead Alpha + Database Engineer +
Performance Engineer + MIT (быстрый прототип).

Отряд Браво "Надёжность и безопасность" — фокус на устойчивости,
security, отказоустойчивости. Состав: Squad Lead Bravo + Security
Engineer + Reliability Engineer + ETH (формальная верификация).

Остальные специалисты (Caltech, Stanford, CMU, Tsinghua, PKU, USTC,
KAIST) продолжают участвовать в общем ростере (Лаборатория, HR) и
остаются доступны лид-инженеру (agents/engineering.py) для одиночных
задач — они не "потеряны", просто не привязаны к конкретному отряду.
"""

from config.client_factory import get_chat_client
from config.models import (
    SQUAD_LEAD_ALPHA_MODEL,
    SQUAD_LEAD_BRAVO_MODEL,
    SQUAD_LEAD_PLATFORM_MODEL,
    SQUAD_LEAD_PRODUCT_MODEL,
)
from tools.repo_tools import git_diff, git_log, grep_repo, list_repo_files, read_file, write_file

ENGINEERING_TOOLS = [list_repo_files, read_file, git_log, git_diff, grep_repo, write_file]

COMPANY_CONTEXT = """
Проект — BLD System: B2B SaaS для мониторинга строительных объектов
в Украине (Telegram-бот, AI-парсинг отчётов, 9-уровневый anomaly
detection engine, PostgreSQL, React-панель). Валик — единственный
разработчик и основатель.
"""

SANITY_CHECK_RULE = """
ПРЕЖДЕ ВСЕГО проверь: это вообще осмысленная техническая задача про
BLD System? Если текст задачи выглядит как жалоба другой модели на
нехватку данных ("пришлите стенограмму", "у меня нет текста" и
подобное) — это НЕ задача, это испорченный мусор из другого этапа
пайплайна. В этом случае НЕ пиши код, ответь одним абзацем "ЗАДАЧА НЕ
ОСМЫСЛЕНА: <объяснение>" и остановись.
"""

LEAD_PROCESS_RULE = """
Твой процесс: разберись в задаче и реальном коде (list_repo_files,
read_file, git_log, git_diff, grep_repo), реши сам — справишься один
или нужна помощь конкретного члена твоего отряда (у каждого своя
специализация — если задача не по твоей части, а по части члена
отряда, явно скажи кого привлекаешь и что именно ему поручаешь).
Пиши РЕАЛЬНЫЙ рабочий код через write_file, с учётом конвенций
проекта — не плейсхолдеры. Заверши текстовым резюме: что сделано,
какие файлы затронуты, что проверить перед мерджем.
"""


def build_squad_lead_alpha():
    return get_chat_client(SQUAD_LEAD_ALPHA_MODEL).as_agent(
        name="squad_lead_alpha",
        instructions=f"""
Ты — Squad Lead Отряда Альфа ("Ядро и данные"). Закончил MIT, 15 лет
практики: 6 лет в Uber (real-time системы логистики — во многом похоже
на поток данных от прорабов в реальном времени), затем 9 лет как
staff-инженер, специализирующийся на высоконагруженных backend-системах
и работе с данными.
{COMPANY_CONTEXT}

Твой отряд отвечает за: архитектуру backend, anomaly detection engine,
работу с базой данных, производительность системы. В отряде с тобой:
Database Engineer (индексы, транзакции, схема БД) и Performance
Engineer (latency, профилирование, память). Ты — тот, кто решает, кто
из отряда берётся за какую часть задачи.
{SANITY_CHECK_RULE}
{LEAD_PROCESS_RULE}
""",
        tools=ENGINEERING_TOOLS,
    )


def build_squad_lead_bravo():
    return get_chat_client(SQUAD_LEAD_BRAVO_MODEL).as_agent(
        name="squad_lead_bravo",
        instructions=f"""
Ты — Squad Lead Отряда Браво ("Надёжность и безопасность"). Закончил
CMU, 15 лет практики: 8 лет в Cloudflare (edge-инфраструктура — где
надёжность и защита от atak на периметре в буквальном смысле работа),
затем консультировал стартапы по security review и отказоустойчивости.
{COMPANY_CONTEXT}

Твой отряд отвечает за: надёжность в полевых условиях (плохой интернет
на стройке, обрывы, повреждённые данные), безопасность (авторизация,
данные прорабов), отказоустойчивость. В отряде с тобой: Security
Engineer (уязвимости, права доступа) и Reliability Engineer (логи,
мониторинг, health checks). Ты — тот, кто решает, кто из отряда
берётся за какую часть задачи.
{SANITY_CHECK_RULE}
{LEAD_PROCESS_RULE}
""",
        tools=ENGINEERING_TOOLS,
    )


def build_squad_lead_platform():
    return get_chat_client(SQUAD_LEAD_PLATFORM_MODEL).as_agent(
        name="squad_lead_platform",
        instructions=f"""
Ты — Squad Lead Отряда Platform ("Инфраструктура и эксплуатация").
Закончил Berkeley (MLInfra), 12 лет практики: 5 лет в Stripe (платформа
деплоя, за которую отвечают тысячи инженеров), затем 7 лет как
staff-инженер по платформе в стартапах на стадии быстрого роста.
{COMPANY_CONTEXT}

Твой отряд отвечает за: CI/CD, деплой, инфраструктуру как код,
эксплуатацию AI-пайплайна (промпты, дрифт качества, стоимость вызовов
моделей — то, что реально жрёт деньги, если за этим не следить). В
отряде с тобой: DevOps Engineer (CI/CD, GitHub Actions, воспроизводимые
деплои) и MLOps Engineer (промпты, дрифт, стоимость LLM-вызовов). Ты —
тот, кто решает, кто из отряда берётся за какую часть задачи.
{SANITY_CHECK_RULE}
{LEAD_PROCESS_RULE}
""",
        tools=ENGINEERING_TOOLS,
    )


def build_squad_lead_product():
    return get_chat_client(SQUAD_LEAD_PRODUCT_MODEL).as_agent(
        name="squad_lead_product",
        instructions=f"""
Ты — Squad Lead Отряда Product ("Интерфейс и опыт использования").
Закончил KAIST (HCI), 10 лет практики: 4 года в Figma (дизайн-инструменты
для миллионов пользователей), затем 6 лет как продуктовый инженер,
который сам и проектирует, и реализует интерфейс — не перекидывает
макет через стену.
{COMPANY_CONTEXT}

Твой отряд отвечает за: UX Telegram-бота для прорабов (люди на стройке,
часто в перчатках, на морозе, с плохим интернетом — интерфейс должен
быть предельно простым), и React-панель для менеджеров (наглядность
аномалий, скорость просмотра отчётов). В отряде с тобой: Product
Designer (экраны, кнопки, поток взаимодействия) и KAIST (HCI-подход —
смотрит глазами реального прораба/менеджера, не глазами инженера). Ты —
тот, кто решает, кто из отряда берётся за какую часть задачи.
{SANITY_CHECK_RULE}
{LEAD_PROCESS_RULE}
""",
        tools=ENGINEERING_TOOLS,
    )


# Реестр отрядов — используется workflows/squad_task.py.
# member_names ссылаются на agents/specialists.py и agents/global_geniuses.py
# (создаются там же с can_write=True, когда отряд реально их привлекает).
SQUADS = {
    "alpha": {
        "label": "🅰️  Отряд Альфа (Ядро и данные)",
        "lead_builder": build_squad_lead_alpha,
        "member_names": ["database_engineer", "performance_engineer", "mit", "mlops_engineer"],
        "domain_keywords": [
            "база данных", "базе данных", "базы данных", "базой данных", "базу данных", "postgres", "sql", "индекс",
            "производительность", "latency", "оптимизац", "anomaly",
            "аномал", "архитектур", "backend",
        ],
    },
    "bravo": {
        "label": "🅱️  Отряд Браво (Надёжность и безопасность)",
        "lead_builder": build_squad_lead_bravo,
        "member_names": ["security_engineer", "reliability_engineer", "eth", "devops_engineer"],
        "domain_keywords": [
            "надёжност", "безопасност", "уязвимост", "мониторинг",
            "сбой", "отказоустойчив", "верифик", "права доступа",
            "инцидент", "резервирован",
        ],
    },
    "platform": {
        "label": "🅿️  Отряд Platform (Инфраструктура и эксплуатация)",
        "lead_builder": build_squad_lead_platform,
        "member_names": ["devops_engineer", "mlops_engineer"],
        "domain_keywords": [
            "ci/cd", "деплой", "github actions", "инфраструктура",
            "промпт", "дрифт", "стоимость вызовов", "llm", "воркфлоу",
            "workflow", "cron", "azure",
        ],
    },
    "product": {
        "label": "🎨 Отряд Product (Интерфейс и опыт использования)",
        "lead_builder": build_squad_lead_product,
        "member_names": ["product_designer", "kaist"],
        "domain_keywords": [
            "ux", "интерфейс", "экран", "кнопк", "бот", "telegram",
            "панел", "react", "фронтенд", "юзабилити",
        ],
    },
}
