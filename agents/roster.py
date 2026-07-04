"""
Единый пул "всех людей компании" — используется режимом Лаборатория
(workflows/lab_session.py) и HR 1-на-1 (workflows/hr_checkin.py), где
участники набираются из ВСЕХ доступных персонажей, а не из одной
фиксированной команды.

Состав:
- Совет директоров (agents/board.py): mekhmat, fiztech, fizmat, tehmat —
  гении с реальным доступом к коду.
- Код-ревью команда (agents/team.py): cto, backend_senior,
  product_frontend, qa_security — тоже с реальным доступом к коду.
- Правление (agents/executive_board.py): coo, hr — без доступа к коду.

Отмечаем отдельно, у кого есть реальный доступ к репозиториям (has_tools),
чтобы Лаборатория могла корректно решать, можно ли этой паре предложить
взяться за реальную техническую проблему из кода, или им доступна
только абстрактная постановка.
"""

from agents.board import build_board
from agents.executive_board import build_executive_board
from agents.team import build_team

# Роли, у которых есть реальный доступ к репозиториям через tools.
CODE_ACCESS_ROLES = {
    "mekhmat", "fiztech", "fizmat", "tehmat",
    "cto", "backend_senior", "product_frontend", "qa_security",
}


def build_full_roster() -> dict:
    """Возвращает dict {role: Agent} со всеми людьми компании разом."""
    roster = {}
    roster.update(build_board())
    roster.update(build_team())
    roster.update(build_executive_board())
    return roster
