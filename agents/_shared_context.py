"""
Единый загрузчик контекста компании — читает context/company_context.md
и отдаёт его всем агентам.

Раньше контекст был скопирован почти одинаковым текстом в 8+ файлов
(agents/board.py, team.py, executive_board.py, specialists.py,
global_geniuses.py, growth_team.py, squads.py, review_gate.py) —
обновлять пришлось бы в 8 местах. Теперь один markdown-файл, который
Валик редактирует напрямую, и все агенты подхватывают изменения при
следующем запуске.

Живёт в коде (context/company_context.md, коммитится в репозиторий),
а не в настройках API/модели — переживёт смену провайдера или модели
без потери контекста.
"""

from functools import lru_cache
from pathlib import Path

_CONTEXT_PATH = Path(__file__).resolve().parent.parent / "context" / "company_context.md"


@lru_cache(maxsize=1)
def load_company_context() -> str:
    """Возвращает содержимое context/company_context.md целиком.
    Кэшируется (lru_cache) — файл читается один раз за процесс, не на
    каждого агента отдельно."""
    if not _CONTEXT_PATH.exists():
        return (
            "(ВНИМАНИЕ: context/company_context.md не найден — "
            "агент работает без контекста компании)"
        )
    return _CONTEXT_PATH.read_text(encoding="utf-8")
