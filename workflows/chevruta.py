"""
Хеврута — свободный формат парного/группового изучения (2-4 человека,
по образцу еврейской традиции совместного разбора текста). В отличие
от Лаборатории (workflows/lab_session.py, которая решает конкретную
проблему из кода) и от Squad Initiative/Individual Initiative (которые
идут к CTO ЗА ОДОБРЕНИЕМ на реализацию) — Хеврута не обязана быть
привязана к текущему коду или задаче вообще. Это исследование гипотезы
или идеи, "что если" — может быть про BLD System, а может быть чисто
техническое любопытство, которое потом даже не обязательно приведёт к
изменению кода.

Тон — позитивный, оптимистичный, но обдуманный: не "давайте писать
код прямо сейчас", а настоящее совместное мышление вслух, где идеи
можно пробовать, ошибаться, разворачивать в неожиданную сторону.

В конце группа сама решает, к кому пойти за реакцией — к "кумиру"
(случайно из CTO/CEO/Chief Scientist — те, кого молодые в компании
реально могли бы уважать) — тот смотрит и говорит: стоит копать
дальше, отдать в реализацию (тогда заводится задача на task board),
или просто интересная мысль, которая пока остаётся мыслью.
"""

import asyncio
import random

from agents.ceo import build_ceo
from agents.roster import build_full_roster
from agents.team import build_team
from tools.telegram_report import send_telegram_report
from workflows._common import curate_knowledge, run_free_conversation
from workflows.task_board import add_task

MAX_TURNS = 10  # чуть больше, чем в Лаборатории — это не решение задачи, а разговор

MENTOR_BUILDERS = {
    "cto": lambda: build_team()["cto"],
    "ceo": build_ceo,
}
MENTOR_LABELS = {"cto": "🧑‍💼 CTO", "ceo": "👑 CEO"}


def pick_group(roster: dict, size_hint: int | None = None) -> list[str]:
    """2-4 человека, с уклоном к меньшим группам (легче договориться)."""
    size = size_hint or random.choices([2, 3, 4], weights=[45, 35, 20])[0]
    return random.sample(list(roster.keys()), k=min(size, len(roster)))


async def spark_hypothesis(group_names: list[str], roster: dict) -> str:
    """Один из группы (случайно) закидывает идею для совместного
    разбора — может быть про BLD, а может быть чисто техническое
    любопытство, не обязанное вести к немедленному изменению кода."""
    opener_name = group_names[0]
    opener = roster[opener_name]

    prompt = f"""
Ты начинаешь хевруту (свободный совместный разбор идеи) с коллегами:
{', '.join(n for n in group_names if n != opener_name)}.

Закинь ОДНУ мысль/гипотезу/идею для совместного обдумывания — не
обязательно проблему из текущего кода, может быть техническое
любопытство, "а что если", наблюдение, которое давно вертелось в
голове. Тон — позитивный, живой, настоящий разговор коллег, а не
формальная постановка задачи. 2-4 предложения.
"""
    response = await opener.run(prompt)
    return response.text.strip()


async def find_mentor_reaction(topic: str, transcript_summary: str) -> tuple[str, str]:
    """Группа сама решает, к кому пойти — случайно из кумиров, но с
    учётом кто реально может дать содержательную реакцию на эту тему."""
    mentor_key = random.choice(list(MENTOR_BUILDERS.keys()))
    mentor = MENTOR_BUILDERS[mentor_key]()
    label = MENTOR_LABELS[mentor_key]

    prompt = f"""
Группа коллег хевруты обсуждала: {topic}

Вот суть их разговора:
{transcript_summary}

Дай свою реакцию как {label.split()[-1]} — коротко и по существу:
стоит ли копать дальше, стоит ли отдать в реализацию (тогда явно
скажи "В РЕАЛИЗАЦИЮ" в начале ответа), или это просто интересная
мысль, которая пока не требует действий. Будь честным, но
поддерживающим — цель не отбить желание думать вслух, а дать
содержательный ориентир.
"""
    response = await mentor.run(prompt)
    return label, response.text.strip()


async def run_chevruta() -> str:
    roster = build_full_roster()
    group_names = pick_group(roster)
    print(f"Хеврута: {', '.join(group_names)}")

    topic = await spark_hypothesis(group_names, roster)
    print(f"\nТема:\n{topic}\n{'=' * 60}")

    participants = [roster[n] for n in group_names]
    transcript = await run_free_conversation(participants, topic, max_turns=MAX_TURNS)

    lines = [f"{m.author_name}: {m.text.strip()}" for m in transcript]
    for line in lines:
        print(f"\n{line}")

    transcript_summary = "\n\n".join(lines)
    print(f"\n{'=' * 60}\nИдём за реакцией к кумиру...")
    mentor_label, reaction = await find_mentor_reaction(topic, transcript_summary)
    print(f"{mentor_label}: {reaction}")

    if "В РЕАЛИЗАЦИЮ" in reaction.upper():
        task_id = add_task(topic, "хеврута: " + "+".join(group_names), status="proposed")
        print(f"Заведена задача на доске: {task_id}")

    report = (
        f"📖 ХЕВРУТА — {', '.join(group_names)}\n\n"
        f"ТЕМА:\n{topic}\n\n"
        f"РАЗГОВОР:\n{transcript_summary[:2500]}\n\n"
        f"{mentor_label}:\n{reaction}"
    )
    send_telegram_report(report)
    await curate_knowledge(f"Хеврута: {', '.join(group_names)}", report)
    return report


async def main():
    await run_chevruta()


if __name__ == "__main__":
    asyncio.run(main())
