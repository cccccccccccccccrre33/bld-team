"""
Единый пул "всех людей компании" — используется режимом Лаборатория
(workflows/lab_session.py) и HR 1-на-1 (workflows/hr_checkin.py), где
участники набираются из ВСЕХ доступных персонажей, а не из одной
фиксированной команды.

Состав:
- Совет директоров (agents/board.py): mekhmat, fiztech, fizmat, tehmat,
  chief_scientist — гении с реальным доступом к коду.
- Код-ревью команда (agents/team.py): cto, backend_senior,
  product_frontend, qa_security — тоже с реальным доступом к коду.
- Правление (agents/executive_board.py): coo, hr, vp_engineering —
  без доступа к коду.
- Глобальные гении (agents/global_geniuses.py): mit, caltech, stanford,
  cmu, tsinghua, pku, ustc, eth, kaist — архетипы мировых топ-вузов.
- Инженерный спецназ (agents/specialists.py): database_engineer,
  performance_engineer, security_engineer, reliability_engineer —
  узкие практические специализации.

Итого 22 человека в общем пуле.

Отмечаем отдельно, у кого есть реальный доступ к репозиториям (has_tools),
чтобы Лаборатория могла корректно решать, можно ли этой паре предложить
взяться за реальную техническую проблему из кода, или им доступна
только абстрактная постановка.
"""

from agents.board import build_board
from agents.executive_board import build_executive_board
from agents.global_geniuses import build_global_roster
from agents.specialists import build_specialist_roster
from agents.squads import build_squad_lead_alpha, build_squad_lead_bravo
from agents.team import build_team

# Роли, у которых есть реальный доступ к репозиториям через tools.
CODE_ACCESS_ROLES = {
    "mekhmat", "fiztech", "fizmat", "tehmat", "chief_scientist",
    "cto", "backend_senior", "product_frontend", "qa_security",
    "mit", "caltech", "stanford", "cmu", "tsinghua", "pku", "ustc", "eth", "kaist",
    "database_engineer", "performance_engineer", "security_engineer", "reliability_engineer",
    "squad_lead_alpha", "squad_lead_bravo",
}


def build_full_roster() -> dict:
    """Возвращает dict {role: Agent} со всеми людьми компании разом
    (27 человек: совет + код-ревью + правление + глобальные гении +
    инженерный спецназ + лиды отрядов)."""
    roster = {}
    roster.update(build_board())
    roster.update(build_team())
    roster.update(build_executive_board())
    roster.update(build_global_roster(can_write=False))
    roster.update(build_specialist_roster(can_write=False))
    roster["squad_lead_alpha"] = build_squad_lead_alpha()
    roster["squad_lead_bravo"] = build_squad_lead_bravo()
    return roster
