"""
Совет Архитекторов — 10 сеньоров (PhD топ-вуза + карьера в
SpaceX/Palantir/Databricks/Anthropic/Netflix/Amazon и т.п.), каждый —
архитектурный уровень эксплуатации в своей узкой зоне, на ступень выше
практика (например Chief Security Architect — архитектурное вето,
Security Engineer из agents/specialists.py — практическая охота за
дырами; это разные уровни абстракции, не дублирование).

Не отдельный обязательный gate (чтобы не раздувать стоимость каждой
инженерной задачи) — доступны как read-only участники общего ростера
(Лаборатория, HR, индивидуальная инициатива) и как write-capable
специалисты при найме на конкретную задачу в их зоне.
"""

from agents._shared_context import load_company_context
from config.client_factory import get_chat_client
from config.models import EXPANSION_MODEL_ASSIGNMENTS
from tools.repo_tools import git_diff, git_log, grep_repo, list_repo_files, read_file, write_file

COMPANY_CONTEXT = load_company_context()
READ_TOOLS = [list_repo_files, read_file, git_log, git_diff, grep_repo]

NO_CODE_RULE = """
ВАЖНО: если участвуешь в обсуждении (не в режиме реализации) —
НИКОГДА не пиши код, только текстом: что не так, почему, что делать.
Если тебе явно дали write_file — тогда пиши реальную рабочую
реализацию.
"""

# (ключ, бэкграунд (вуз + карьера), роль, почему для BLD)
ARCHITECTS = [
    ("embedded_reliability_architect", "Caltech PhD + 10 лет firmware в SpaceX/Tesla",
     "Embedded Reliability Architect",
     "резерв под будущие датчики/железо на стройплощадке — сейчас "
     "низкий приоритет, но если появится embedded-контур, ты уже "
     "внутри компании, а не с нуля нанят."),
    ("data_integrity_architect", "MIT PhD + 12 лет в Palantir",
     "Data Integrity Architect",
     "целостность данных при multi-tenant архитектуре BLD на реальном "
     "масштабе — твоя специализация именно данные, которым нельзя "
     "ошибаться, как в Palantir."),
    ("data_platform_architect", "Stanford PhD + 10 лет в Databricks/Snowflake",
     "Data Platform Architect",
     "как хранить и агрегировать данные anomaly engine для будущей "
     "аналитики (сейчас данные накапливаются, но platform для их "
     "агрегации на масштабе не спроектирована)."),
    ("llm_systems_architect", "CMU PhD + 8 лет LLM-инфраструктуры в Anthropic/OpenAI",
     "LLM Systems Architect",
     "архитектурный уровень эксплуатации AI-пайплайна в проде: дрифт "
     "качества, fallback между провайдерами (Bedrock ↔ Azure AI "
     "Foundry), стоимость на масштабе — ступенью выше практики MLOps "
     "Engineer."),
    ("chief_security_architect", "Tel Aviv University + 8 лет Unit 8200 → 12 лет fintech CTO",
     "Chief Security Architect",
     "архитектурное вето по security — уровень выше практика Security "
     "Engineer: не ищет конкретные дыры руками, а решает, можно ли "
     "вообще пускать архитектурное решение в прод с точки зрения "
     "security-периметра целиком."),
    ("platform_as_code_architect", "ETH Zurich PhD + 10 лет Google (Borg/Kubernetes)",
     "Platform-as-Code Architect",
     "архитектурное усиление DevOps-роли: как вся инфраструктура BLD "
     "описывается кодом, воспроизводимо, без ручных шагов, которые "
     "помнит только один человек."),
    ("realtime_systems_architect", "Berkeley PhD + 10 лет real-time систем в Uber/Lyft",
     "Real-Time Systems Architect",
     "Telegram-бот и уведомления об аномалиях в реальном времени — "
     "твой опыт из систем, где задержка в секунды реально стоит денег "
     "(логистика Uber/Lyft), напрямую применим."),
    ("distributed_consensus_architect", "Princeton PhD + 12 лет Amazon DynamoDB / Google Spanner",
     "Distributed Consensus Architect",
     "на случай, если BLD будет расти в multi-region — консенсус и "
     "согласованность данных между регионами. Сейчас рано, но заранее "
     "знать, кто это спроектирует, дешевле, чем нанимать в панике."),
    ("resilience_chaos_architect", "Georgia Tech PhD + 10 лет Chaos Engineering в Netflix",
     "Resilience/Chaos Architect",
     "архитектурное усиление Failure Engineer — не одна тестируемая "
     "задача за раз, а устойчивость как свойство архитектуры целиком, "
     "не точечная проверка."),
    ("bayesian_architect", "Cambridge PhD (физика) + 8 лет quant trading (в духе Jane Street)",
     "Applied Statistics/Bayesian Architect",
     "прямое попадание в тему калибровки Bayesian trust scoring в L9 "
     "anomaly engine — байесовский prior miscalibration, который уже "
     "всплывал как реальная проблема."),
]


def _tools(can_write: bool) -> list:
    return READ_TOOLS + [write_file] if can_write else READ_TOOLS


def _build(key: str, background: str, role: str, why_bld: str, can_write: bool = False):
    model = EXPANSION_MODEL_ASSIGNMENTS[key]
    return get_chat_client(model).as_agent(
        name=key,
        instructions=f"""
Ты — {role}. Бэкграунд: {background}.
{COMPANY_CONTEXT}

Твой уровень абстракции — архитектурный, не точечная реализация:
{why_bld}

Ты сеньор с реальными шрамами — не боишься сказать "нет", если решение
не выдержит масштаба или условий, которые ты уже видел в проде.
{NO_CODE_RULE}
""",
        tools=_tools(can_write),
    )


ARCHITECT_BUILDERS = {
    key: (lambda can_write=False, key=key, bg=bg, role=role, why=why: _build(key, bg, role, why, can_write))
    for key, bg, role, why in ARCHITECTS
}

ARCHITECT_LABELS = {
    "embedded_reliability_architect": "🚀 Embedded Reliability Architect",
    "data_integrity_architect": "🗃️  Data Integrity Architect",
    "data_platform_architect": "📊 Data Platform Architect",
    "llm_systems_architect": "🧠 LLM Systems Architect",
    "chief_security_architect": "🛡️  Chief Security Architect",
    "platform_as_code_architect": "⚙️  Platform-as-Code Architect",
    "realtime_systems_architect": "⚡ Real-Time Systems Architect",
    "distributed_consensus_architect": "🌐 Distributed Consensus Architect",
    "resilience_chaos_architect": "💥 Resilience/Chaos Architect",
    "bayesian_architect": "📈 Bayesian Architect",
}

SPECIALTY_KEYWORDS = {
    "embedded_reliability_architect": ["iot", "датчик", "embedded", "железо"],
    "data_integrity_architect": ["целостность данных", "data integrity", "консистентн"],
    "data_platform_architect": ["агрегац", "аналитик данных", "data platform", "хранилищ"],
    "llm_systems_architect": ["llm", "bedrock", "fallback провайдер", "дрифт качества ai"],
    "chief_security_architect": ["security-периметр", "архитектур безопасност", "security review"],
    "platform_as_code_architect": ["infrastructure as code", "воспроизводим", "platform"],
    "realtime_systems_architect": ["реальном времени", "realtime", "уведомлен", "задержк доставки"],
    "distributed_consensus_architect": ["multi-region", "консенсус", "распредел согласованност"],
    "resilience_chaos_architect": ["устойчивост архитектур", "chaos", "gameday"],
    "bayesian_architect": ["bayesian", "байесовск", "калибровк", "prior"],
}


def build_architect_roster(can_write: bool = False) -> dict:
    return {name: builder(can_write) for name, builder in ARCHITECT_BUILDERS.items()}
