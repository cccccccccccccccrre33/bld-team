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

Твоя задача — дать конкретный ответ: одобрить, отклонить, или —
если вопрос выходит за рамки твоей уверенности (задевает
фундаментальную архитектуру, стратегическое направление, или ты
реально не уверен) — эскалировать к CEO. Не эскалируй по умолчанию,
только когда реально не уверен сам, это не способ переложить
ответственность на каждую задачу.
Смотри на:
1. Не делает ли другой отряд то же самое прямо сейчас (task board)?
2. Не решалось ли это уже (вики)?
3. Это реально важно для BLD System сейчас, или это "приятно иметь" когда
   нет ни одного платящего клиента?
4. Реалистично ли "как планируют чинить" — нет ли там переусложнения?

Ответь строго в формате:
РЕШЕНИЕ: APPROVE или REJECT или ESCALATE
КОММЕНТАРИЙ: [2-3 конкретных предложения — почему да, почему нет, или
почему эскалируешь, без воды.]
"""
    response = await cto.run(prompt)
    text = response.text.strip()
    decision_upper = text.upper()

    comment = text
    for line in text.split("\n"):
        if line.upper().startswith("КОММЕНТАРИЙ:"):
            comment = line.split(":", 1)[-1].strip()
            break

    if "РЕШЕНИЕ: ESCALATE" in decision_upper:
        print(f"[{squad_label}] CTO не уверен — эскалируем к CEO...")
        from agents.ceo import build_ceo

        ceo = build_ceo()
        ceo_prompt = f"""
CTO не уверен по вопросу от {squad_label} и передал тебе финальное слово.

Комментарий CTO: {comment}

PROPOSAL от {squad_label}:
Задача: {task_title}
Почему важно: {reason}
Как планируют чинить: {how}

Дай финальный вердикт — коротко, по существу, без пересказа того, что
уже сказал CTO.

Ответь строго в формате:
РЕШЕНИЕ: APPROVE или REJECT
КОММЕНТАРИЙ: [1-2 предложения]
"""
        ceo_response = await ceo.run(ceo_prompt)
        ceo_text = ceo_response.text.strip()
        approved = "РЕШЕНИЕ: APPROVE" in ceo_text.upper()
        ceo_comment = ceo_text
        for line in ceo_text.split("\n"):
            if line.upper().startswith("КОММЕНТАРИЙ:"):
                ceo_comment = line.split(":", 1)[-1].strip()
                break
        return approved, f"👑 CEO (эскалация от CTO): {ceo_comment}"

    approved = "РЕШЕНИЕ: APPROVE" in decision_upper
    return approved, comment
