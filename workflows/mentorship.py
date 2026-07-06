"""
Менторство — единственный процесс в компании, посвящённый развитию
людей, а не решению задач. Engineering Mentor раз в цикл смотрит на
вики компании (.state/company_wiki.md — туда пишут итоги заседаний,
Лаборатории, инженерных задач) и даёт персональную обратную связь
одному случайному молодому специалисту (agents/global_geniuses.py).

Если в вики почти нет упоминаний этого человека — ментор честно так и
говорит, а не выдумывает несуществующие достижения.
"""

import asyncio
import random
from pathlib import Path

from agents.global_geniuses import GENIUS_BUILDERS, GLOBAL_LABELS
from agents.growth_team import build_engineering_mentor
from tools.telegram_report import send_telegram_report
from workflows._common import curate_knowledge

STATE_DIR = Path(".state")
WIKI_PATH = STATE_DIR / "company_wiki.md"


async def run_mentorship_checkin() -> str:
    young_name = random.choice(list(GENIUS_BUILDERS.keys()))
    label = GLOBAL_LABELS.get(young_name, young_name)

    wiki_text = (
        WIKI_PATH.read_text(encoding="utf-8")
        if WIKI_PATH.exists()
        else "(вики пока пустая — компания только начинает работать)"
    )
    wiki_excerpt = wiki_text[-6000:]  # не раздуваем промпт

    mentor = build_engineering_mentor()

    prompt = f"""
Вот текущая вики компании (последние записи о решениях/находках):

{wiki_excerpt}

Найди упоминания вклада {label} (молодой специалист, недавний
выпускник). Если находишь конкретные упоминания — дай ему личную,
конкретную обратную связь по росту: что сильное, что пока слабое
место. Если упоминаний почти нет — честно скажи об этом и что стоило
бы активнее участвовать в Лаборатории — НЕ выдумывай несуществующие
достижения.

Обращайся напрямую к {label}, как будто говоришь с ним лично — тепло,
но по существу, без общих слов вроде "молодец". 4-6 предложений.
"""
    response = await mentor.run(prompt)
    feedback = response.text.strip()

    message = f"🎓 ENGINEERING MENTOR → {label}\n\n{feedback}"
    send_telegram_report(message)
    await curate_knowledge(f"Менторство: {label}", feedback)
    return message


async def main():
    print("Engineering Mentor выбирает, с кем поговорить о росте...")
    message = await run_mentorship_checkin()
    print(message)


if __name__ == "__main__":
    asyncio.run(main())
