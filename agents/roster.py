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
- Глобальные гении (agents/global_geniuses.py): mit, caltech, stanford,
  cmu, tsinghua, pku, ustc, eth — архетипы мировых топ-вузов, тоже с
  реальным доступом к коду (read-only — в Лаборатории код не пишут,
  только разбирают теоретически, как и остальные).

Итого 16 человек в общем пуле.

Отмечаем отдельно, у кого есть реальный доступ к репозиториям (has_tools),
чтобы Лаборатория могла корректно решать, можно ли этой паре предложить
взяться за реальную техническую проблему из кода, или им доступна
только абстрактная постановка.
"""

from agents.board import build_board
from agents.executive_board import build_executive_board
from agents.global_geniuses import build_global_roster
from agents.team import build_team

# Роли, у которых есть реальный доступ к репозиториям через tools.
CODE_ACCESS_ROLES = {
    "mekhmat", "fiztech", "fizmat", "tehmat",
    "cto", "backend_senior", "product_frontend", "qa_security",
    "mit", "caltech", "stanford", "cmu", "tsinghua", "pku", "ustc", "eth",
}


def build_full_roster() -> dict:
    """Возвращает dict {role: Agent} со всеми людьми компании разом
    (16 человек: совет + код-ревью + правление + глобальные гении)."""
    roster = {}
    roster.update(build_board())
    roster.update(build_team())
    roster.update(build_executive_board())
    roster.update(build_global_roster(can_write=False))  # в ростере — только читают, не пишут код
    return roster
