"""
CTO Approval Gate — реальный рычаг иерархии, не декорация.

Когда отряд самостоятельно находит задачу (workflows/squad_initiative.py),
он сначала приходит к CTO с proposal:
  - Что нашли (title)
  - Почему это важно (reason)
  - Как планируют чинить (how)

CTO (из код-ревью команды, agents/team.py) анализирует это в контексте:
  1. Task Board — что уже в работе, нет ли дублирования
  2. Вики компании — что уже решалось, какие были решения
  3. Своей архитектурной позиции (20 лет Google + Amazon)

Результат: APPROVE (задача идёт на выполнение) или REJECT + причина.

Исключение: мелкие задачи (minor_fix=True) отряд берёт сам без approval —
это сознательное доверие специалистам в их зоне (как в реальной компании
junior-фиксы не требуют senior sign-off). Порог "мелкая" — субъективная
оценка самого отряда (честность — часть культуры).
"""

from agents.team import build_team
from workflows.task_board import get_board_summary


async def cto_approval(
    squad_label: str,
    task_title: str,
    reason: str,
    how: str,
) -> tuple[bool, str]:
    """Возвращает (approved: bool, cto_comment: str).

    CTO читает task board (контекст что уже в работе), вики (что уже
    решалось) и даёт конкретный ответ с обоснованием.
    """
    from pathlib import Path

    wiki_text = ""
    wiki_path = Path(".state/company_wiki.md")
    if wiki_path.exists():
        full = wiki_path.read_text(encoding="utf-8")
        wiki_text = full[-4000:]  # последние записи

    board_summary = get_board_summary()

    team = build_team()
    cto = team["cto"]

    prompt = f"""
Ты — CTO. К тебе пришёл {squad_label} с предложением задачи.

ТЕКУЩАЯ ДОСКА ЗАДАЧ (что сейчас в работе и что ждёт):
{board_summary}

ПОСЛЕДНИЕ ЗАПИСИ ВИКИ КОМПАНИИ (что уже решалось):
{wiki_text if wiki_text else "(вики пока пустая)"}

PROPOSAL от {squad_label}:
Задача: {task_title}
Почему важно: {reason}
Как планируют чинить: {how}

Твоя задача — дать конкретный ответ: одобрить или отклонить.
Смотри на:
1. Не делает ли другой отряд то же самое прямо сейчас (task board)?
2. Не решалось ли это уже (вики)?
3. Это реально важно для BLD System сейчас, или это "приятно иметь" когда
   нет ни одного платящего клиента?
4. Реалистично ли "как планируют чинить" — нет ли там переусложнения?

Ответь строго в формате:
РЕШЕНИЕ: APPROVE или REJECT
КОММЕНТАРИЙ: [2-3 конкретных предложения — почему да или почему нет,
без воды. Если REJECT — что именно не так и стоит ли переформулировать.]
"""
    response = await cto.run(prompt)
    text = response.text.strip()

    approved = "РЕШЕНИЕ: APPROVE" in text.upper()
    # Извлекаем комментарий
    comment = text
    for line in text.split("\n"):
        if line.upper().startswith("КОММЕНТАРИЙ:"):
            comment = line.split(":", 1)[-1].strip()
            break

    return approved, comment
