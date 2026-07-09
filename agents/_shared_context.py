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
    """Возвращает содержимое context/company_context.md целиком —
    ТОЛЬКО для Правления (executive_board.py), где обсуждение трёх
    проектов и приоритетов между ними реально уместно."""
    if not _CONTEXT_PATH.exists():
        return (
            "(ВНИМАНИЕ: context/company_context.md не найден — "
            "агент работает без контекста компании)"
        )
    return _CONTEXT_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_bld_scope_context() -> str:
    """Возвращает контекст компании БЕЗ секции 'Кто мы' (там
    упоминаются Хвиля и Нейробариста) — для ВСЕХ технических ролей
    (совет директоров, отряды, инженеры, специалисты, ревью, гении).

    Раньше все технические агенты читали load_company_context()
    целиком и из-за этого могли рассуждать про "какой из трёх проектов
    закрыть" — бизнес-решение не по адресу для чисто технической роли.
    Эта функция вырезает секцию между '## Кто мы' и следующим '## ' —
    остальной технический контент (архитектура, стек, культура
    команды) остаётся."""
    full = load_company_context()
    lines = full.split("\n")
    result = []
    skipping = False
    for line in lines:
        if line.strip() == "## Кто мы":
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            result.append(line)

    scoped = "\n".join(result)
    scope_note = (
        "\n> Примечание: ты работаешь СТРОГО в рамках BLD System "
        "(репозитории bld-system и bld-panel). Другие проекты "
        "компании (если такие есть) — не твоя зона ответственности "
        "и не должны фигурировать в твоих задачах и рекомендациях.\n"
    )
    return scope_note + scoped
