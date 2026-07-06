"""
HR 1-на-1 — HR реально "вызывает" одного случайного человека из всей
компании (совет директоров, код-ревью команда или COO) на приватный
разговор, а не участвует в общегрупповом обсуждении.

Формат — не спор, а интервью: HR задаёт вопрос, собеседник отвечает,
HR слушает и уточняет. В конце — короткая заметка для Валика: как
человек, что его беспокоит/мотивирует, если что-то всплыло важное.
"""

import asyncio
import random

from agent_framework import Message

from agents.executive_board import build_executive_board
from agents.global_geniuses import GLOBAL_LABELS
from agents.growth_team import GROWTH_LABELS
from agents.specialists import SPECIALIST_LABELS
from agents.roster import build_full_roster
from config.models import EXEC_MODEL_ASSIGNMENTS
from config.client_factory import get_chat_client
from tools.telegram_report import send_telegram_report
from workflows._common import ask

MAX_EXCHANGES = 5  # вопрос-ответ пар — это разговор, не допрос

ROLE_LABELS = {
    "mekhmat": "🔢 Мехмат", "fiztech": "⚙️  Физтех",
    "fizmat": "🎲 Физмат", "tehmat": "♟️  Техмат", "chief_scientist": "🔭 Chief Scientist",
    "cto": "🧑‍💼 CTO", "backend_senior": "⌨️  Backend",
    "product_frontend": "🎨 Product/Frontend", "qa_security": "🔒 QA/Security",
    "coo": "🗂️  COO", "hr": "🧑‍🤝‍🧑 HR", "vp_engineering": "📐 VP Engineering", "squad_lead_alpha": "🅰️  Squad Lead Alpha", "squad_lead_bravo": "🅱️  Squad Lead Bravo",
    **GLOBAL_LABELS,
    **SPECIALIST_LABELS,
    **GROWTH_LABELS,
}


async def run_interview(hr_agent, interviewee_agent, interviewee_name: str) -> list[Message]:
    """HR ведёт разговор 1-на-1: чередование вопрос (HR) -> ответ
    (собеседник), с полной историей на каждом шаге."""

    history: list[Message] = [
        Message(
            role="user",
            contents=[
                f"Ты — HR. Ты только что позвал {interviewee_name} на короткий "
                "личный разговор (не рабочее совещание, а просто узнать как "
                "дела). Начни разговор — тепло, неформально, с открытого "
                "вопроса о том, как у него дела в последнее время, что его "
                "занимает или беспокоит. 2-3 предложения."
            ],
        )
    ]
    transcript: list[Message] = []

    speaker_order = [hr_agent, interviewee_agent]
    for i in range(MAX_EXCHANGES * 2):
        agent = speaker_order[i % 2]
        response = await agent.run(history)
        msg = Message(role="assistant", contents=[response.text], author_name=agent.name)
        history.append(msg)
        transcript.append(msg)

    return transcript


async def compile_hr_note(interviewee_name: str, transcript: list[Message]) -> str:
    """Короткая человеческая заметка HR по итогам разговора — не отчёт
    в смысле KPI, а именно "что HR вынес из разговора"."""
    client = get_chat_client(EXEC_MODEL_ASSIGNMENTS["hr"])

    conv = "\n\n".join(
        f"{ROLE_LABELS.get(m.author_name or '', m.author_name)}: {m.text.strip()}"
        for m in transcript
    )

    prompt = f"""
Вот стенограмма личного разговора HR с {interviewee_name}:

{conv}

Составь короткую заметку для Валика от лица HR (без markdown-звёздочек,
простой текст для Telegram):

🧑‍🤝‍🧑 HR: разговор с {ROLE_LABELS.get(interviewee_name, interviewee_name)}

ЧТО УЗНАЛ:
[2-3 предложения — суть того, что человек рассказал, его настрой]

СТОИТ ЛИ ВАЛИКУ ОБРАТИТЬ ВНИМАНИЕ:
[Если реально что-то важное всплыло — конкретно что. Если разговор был
просто рутинным чек-ином без ничего примечательного — честно напиши
"ничего особенного, обычный чек-ин" — не выдумывай значимость]

Пиши по-русски, тепло, коротко. Общий объём — не больше 500 символов.
"""
    return await ask(client, prompt)


async def main():
    roster = build_full_roster()
    # HR не может позвать сам себя или COO дважды подряд — берём из
    # полного ростера минус hr.
    candidates = [n for n in roster.keys() if n != "hr"]
    interviewee_name = random.choice(candidates)

    exec_board = build_executive_board()
    hr_agent = exec_board["hr"]
    interviewee_agent = roster[interviewee_name]

    print(f"HR вызывает на разговор: {interviewee_name}")
    transcript = await run_interview(hr_agent, interviewee_agent, interviewee_name)

    for msg in transcript:
        label = ROLE_LABELS.get(msg.author_name or "", msg.author_name or "?")
        print(f"\n{label}: {msg.text}")

    print("\n" + "=" * 60)
    note = await compile_hr_note(interviewee_name, transcript)
    print(note)

    send_telegram_report(note)


if __name__ == "__main__":
    asyncio.run(main())
