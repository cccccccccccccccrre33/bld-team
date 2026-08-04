"""
Единый пул "всех людей компании" — используется режимом Лаборатория
(workflows/lab_session.py) и HR 1-на-1 (workflows/hr_checkin.py).

Engineering Mentor (agents/growth_team.py) сюда НЕ входит — у него
отдельный воркфлоу (workflows/mentorship.py), он не участвует в общих
дискуссиях/спорах, только даёт персональную обратную связь молодым.
"""

from agents.architecture_council import build_architect_roster
from agents.board import build_board
from agents.engineering_fellows import build_fellows_roster
from agents.executive_board import build_executive_board
from agents.expansion_geniuses import build_global_roster as build_expansion_roster
from agents.global_elite import GLOBAL_ELITE_1_KEYS, build_global_elite_1_roster
from agents.global_elite_100 import GLOBAL_ELITE_2_KEYS, build_global_elite_2_roster
from agents.global_elite_3 import GLOBAL_ELITE_3_KEYS, build_global_elite_3_roster
from agents.global_elite_4 import GLOBAL_ELITE_4_KEYS, build_global_elite_4_roster
from agents.global_elite_5 import GLOBAL_ELITE_5_KEYS, build_global_elite_5_roster
from agents.global_elite_6 import GLOBAL_ELITE_6_KEYS, build_global_elite_6_roster
from agents.global_geniuses import build_global_roster
from agents.gtm import build_gtm_lead
from agents.growth_team import build_growth_roster
from agents.specialists import build_specialist_roster
from agents.squads import (
    build_squad_lead_alpha,
    build_squad_lead_bravo,
    build_squad_lead_platform,
    build_squad_lead_product,
)
from agents.team import build_team
from agents.custom_agents import disabled_roles, load_custom_agents

CODE_ACCESS_ROLES = {
    "mekhmat", "fiztech", "fizmat", "tehmat", "chief_scientist", "ceo",
    "cto", "backend_senior", "product_frontend", "qa_security",
    "mit", "caltech", "stanford", "cmu", "tsinghua", "pku", "ustc", "eth", "kaist",
    "database_engineer", "performance_engineer", "security_engineer", "reliability_engineer",
    "squad_lead_alpha", "squad_lead_bravo", "squad_lead_platform", "squad_lead_product",
    "mlops_engineer", "devops_engineer", "product_designer",
    "technion", "polytechnique", "utokyo", "berkeley_mlinfra", "toronto",
    "itmo", "oxford", "iit_bombay", "nus", "waterloo_prod",
    "embedded_reliability_architect", "data_integrity_architect",
    "data_platform_architect", "llm_systems_architect", "chief_security_architect",
    "platform_as_code_architect", "realtime_systems_architect",
    "distributed_consensus_architect", "resilience_chaos_architect", "bayesian_architect",
    "principal_systems_architect", "physics_informed_ml_engineer",
    "language_compiler_architect", "data_storage_alchemist",
    "algorithmic_performance_sorcerer", "security_crypto_architect",
    "formal_correctness_engineer", "embedded_edge_engineer",
    *GLOBAL_ELITE_1_KEYS, *GLOBAL_ELITE_2_KEYS, *GLOBAL_ELITE_3_KEYS, *GLOBAL_ELITE_4_KEYS,
    *GLOBAL_ELITE_5_KEYS, *GLOBAL_ELITE_6_KEYS,
}


def build_full_roster() -> dict:
    """Возвращает dict {role: Agent} со всеми людьми компании (~612:
    59 исходных + 50 Global Elite I + 100 Global Elite II +
    100 Global Elite III + 100 Global Elite IV + 100 Global Elite V +
    100 Global Elite VI + 2 новых лида отрядов Platform/Product + GTM Lead)."""
    roster = {}
    roster.update(build_board())
    roster.update(build_team())
    roster.update(build_executive_board())
    roster.update(build_global_roster(can_write=False))
    roster.update(build_specialist_roster(can_write=False))
    roster.update(build_growth_roster(can_write=False))
    roster.update(build_expansion_roster(can_write=False))
    roster.update(build_architect_roster(can_write=False))
    roster.update(build_fellows_roster(can_write=False))
    roster.update(build_global_elite_1_roster(can_write=False))
    roster.update(build_global_elite_2_roster(can_write=False))
    roster.update(build_global_elite_3_roster(can_write=False))
    roster.update(build_global_elite_4_roster(can_write=False))
    roster.update(build_global_elite_5_roster(can_write=False))
    roster.update(build_global_elite_6_roster(can_write=False))
    roster["squad_lead_alpha"] = build_squad_lead_alpha()
    roster["squad_lead_bravo"] = build_squad_lead_bravo()
    roster["squad_lead_platform"] = build_squad_lead_platform()
    roster["squad_lead_product"] = build_squad_lead_product()
    roster["gtm_lead"] = build_gtm_lead()

    # Кастомные агенты пользователя (config/custom_agents.yaml) — та же
    # логика "добавить кого хочешь без правки кода", что и в team.py.
    roster.update(load_custom_agents())

    disabled = disabled_roles()
    if disabled:
        roster = {k: v for k, v in roster.items() if k not in disabled}
    return roster
