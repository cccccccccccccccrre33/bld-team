"""
Гильдии и Research & Fundamentals — НЕ департаменты (agents/squads.py):
не отвечают за код, не роутятся автоматически на баги, не имеют
write-доступа сверх того, что человек уже имеет через свой департамент
или Architecture Council. Это площадки обмена опытом и консультации,
аналог "Лаборатории" (agents/specialists.py) — формализовано при
проектировании 7 департаментов, полный разбор в
bld-team-departments.md.

Использование: когда CTO, Совет директоров или лид департамента хотят
явно позвать кого-то "со стороны" на консультацию по RFC или спорному
архитектурному вопросу — эти списки подсказывают, у кого профильный
опыт, без необходимости нанимать нового человека или создавать
отдельную бюрократию. Все перечисленные здесь люди и так доступны
через общий пул agents/engineering.py::build_specialist_pool() — этот
модуль не создаёт новых агентов, только именует существующих под
конкретную консультативную роль.
"""

from agents.global_elite_3 import ELITE_ROSTER_3
from agents.global_elite_4 import ELITE_ROSTER_4
from agents.global_elite_6 import ELITE_ROSTER_6

# Research & Fundamentals — консультативная гильдия без write:
# фундаментальная математика/физика/доменная стройэкспертиза, питает
# Совет директоров и RFC-обсуждения. Кластеры по индексам совпадают с
# порядком в исходных ELITE_ROSTER_N (см. cluster-комментарии в самих
# файлах agents/global_elite_3.py / _4.py / _6.py):
#   ELITE_ROSTER_3[90:100] — "исследования и фундаментальная математика"
#   ELITE_ROSTER_4[80:90]  — "физика и математическое моделирование"
#   ELITE_ROSTER_6[0:40]   — математики (0:20) + физики (20:40), кластеры 1-2
#   ELITE_ROSTER_3[60:70]  — "предметная область и строительная инженерия"
RESEARCH_FUNDAMENTALS_KEYS = (
    [key for key, *_ in ELITE_ROSTER_3[90:100]]
    + [key for key, *_ in ELITE_ROSTER_4[80:90]]
    + [key for key, *_ in ELITE_ROSTER_6[0:40]]
    + [key for key, *_ in ELITE_ROSTER_3[60:70]]
)

# 10 архитекторов Architecture Council (agents/architecture_council.py)
# уже read-only консультанты по построению — формально тоже часть этой
# гильдии, отдельно не дублируем список здесь, см. ARCHITECT_BUILDERS.
RESEARCH_FUNDAMENTALS_HEAD = "chief_scientist"  # Совет директоров, agents/board.py

GUILDS = {
    "performance": {
        "label": "⚡ Гильдия производительности",
        "description": "Обмен опытом по ускорению кода/запросов/инференса между департаментами.",
        "member_names": [
            "bayesian_architect", "janestreet_nanosecond_optimizer",
            "asml_precision_calibration_engineer", "intel_compute_model_architect",
        ],
    },
    "formal_methods": {
        "label": "🔒 Гильдия формальных методов",
        "description": "TLA+/Coq/формальная верификация — консультации по самым критичным модулям.",
        "member_names": [
            "oxford", "oxford_formal_logic", "inria_formal_verification_engineer",
            "platform_as_code_architect",
        ],
    },
    "construction_domain": {
        "label": "🏗️  Гильдия строительного домена",
        "description": "Проверяют физическую/инженерную состоятельность моделей — не пишут код напрямую.",
        "member_names": (
            [key for key, *_ in ELITE_ROSTER_3[60:70]]
            + ["imperial_fluid_dynamics", "som_load_bearing_engineer"]
        ),
    },
    "mentorship": {
        "label": "🎓 Гильдия наставничества",
        "description": "Уже существует как Engineering Mentor (agents/growth_team.py) — без изменений.",
        "member_names": ["engineering_mentor"],
    },
}
