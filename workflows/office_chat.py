"""
Офисные посиделки — неформальный разговор команды о проекте.

Отличие от workflows/discussion.py и board_meeting.py: нет заранее
заданной темы/повестки. Один случайный участник ("искра") сам лезет
в реальный код (bld-system или bld-panel, тоже случайно), находит что-то,
за что зацепиться, и просто начинает разговор об этом — не обязательно
проблему, может быть что угодно любопытное.

Дальше — свободный чат остальных троих, без формальной цели прийти
к решению. В конце — отчёт в Telegram в стиле "что было в офисе сегодня",
а не протокол заседания.
"""

import asyncio
import random
import sys

from agent_framework import Message
from agent_framework.orchestrations import GroupChatBuilder

from agents.office_chat import build_office_chat_team, CONTEXT_PREAMBLE
from config.client_factory import get_chat_client
from config.models import OFFICE_MODEL_ASSIGNMENTS
from tools.repo_tools import git_log, grep_repo, list_repo_files, read_file
from tools.telegram_report import send_telegram_report
from workflows._common import ask, extract_messages, sync_repos_or_alert

MAX_MESSAGES = 12  # это чат, не заседание — держим коротко

ROLE_LABELS = {
    "cto": "🧑‍💼 CTO",
    "backend_senior": "⌨️  Backend",
    "product_frontend": "🎨 Product/Frontend",
    "qa_security": "🔒 QA/Security",
}

SPARK_TOOLS = [list_repo_files, read_file, git_log, grep_repo]


async def find_spark(repo_hint: str | None) -> tuple[str, str]:
    """"Искра" сама копается в случайном репо и находит повод для разговора.
    Возвращает (имя_агента_зачинщика, реплика-затравка)."""

    starter_role = random.choice(["cto", "backend_senior", "product_frontend", "qa_security"])
    repo = repo_hint or random.choice(["bld-system", "bld-panel"])

    client = get_chat_client(OFFICE_MODEL_ASSIGNMENTS["spark"])
    spark_agent = client.as_agent(
        name="spark",
        instructions="Ты помогаешь найти живой повод для разговора, копаясь в реальном коде.",
        tools=SPARK_TOOLS,
    )

    prompt = f"""
{CONTEXT_PREAMBLE}

Ты сейчас в роли: {starter_role}. У тебя есть доступ к репозиторию
{repo} через tools (list_repo_files, read_file, git_log, grep_repo).

Загляни в репозиторий (посмотри последние коммиты, пробегись по паре
файлов, что реально заинтересует человека с твоей профессиональной
специализацией) и найди ОДНУ конкретную вещь, за которую цепляешься —
не обязательно проблему, это может быть что угодно: странный
комментарий, забавный TODO, неожиданно изящное решение, старый костыль,
интересный коммит.

Напиши короткую (2-4 предложения) реплику, с которой ты заходишь
в разговор с коллегами — как будто просто подошёл и сказал вслух.
Разговорный тон, не отчёт. Не пиши преамбулу вроде "вот моя находка" —
сразу говори как в жизни.
"""
    response = await spark_agent.run(prompt)
    return starter_role, response.text.strip()


def build_chat_workflow(team: dict):
    moderator_client = get_chat_client(OFFICE_MODEL_ASSIGNMENTS["moderator"])
    moderator_agent = moderator_client.as_agent(
        name="moderator",
        instructions="""
Ты просто следишь за очередностью в неформальном чате коллег
(cto, backend_senior, product_frontend, qa_security). Это не совещание —
не нужно строго идти по повестке.

Правила:
- Кого-то упомянули/задали вопрос → ему слово.
- Если разговор явно затих или тема исчерпана → можно завершить,
  не обязательно доводить до "вывода".
- Не давай одному говорить больше двух раз подряд без причины.
- Это чат, не протокол — можно завершить и раньше лимита, если люди
  явно закруглились ("ну ладно, я пошёл кофе доливать" и т.п.).
""",
    )

    def stop_condition(messages: list[Message]) -> bool:
        return len([m for m in messages if m.role == "assistant"]) >= MAX_MESSAGES

    return (
        GroupChatBuilder(
            participants=list(team.values()),
            orchestrator_agent=moderator_agent,
            termination_condition=stop_condition,
        )
        .build()
    )


async def compile_chat_report(starter_role: str, spark_line: str, transcript: list[Message]) -> str:
    """Форматирует переписку в стиле 'что было в офисе', а не протокол."""
    client = get_chat_client(OFFICE_MODEL_ASSIGNMENTS["moderator"])

    lines = [f"{ROLE_LABELS.get(starter_role, starter_role)}: {spark_line}"]
    for m in transcript:
        if m.role != "assistant":
            continue
        name = m.author_name or "unknown"
        label = ROLE_LABELS.get(name, name)
        lines.append(f"{label}: {m.text.strip()}")
    chat_text = "\n\n".join(lines)

    prompt = f"""
Вот реальная переписка команды за сегодня (в свободное время, не по
расписанию совещаний):

{chat_text}

Оформи это для Валика как короткую заметку "что было в офисе" —
НЕ протокол, а лёгкий пересказ живого разговора, сохраняя характер
и конкретику (что именно нашли в коде, если это упоминалось).

Формат (без markdown-звёздочек, простой текст для Telegram):

☕ В ОФИСЕ СЕГОДНЯ

[2-3 предложения — с чего начался разговор и о чём в итоге зашла речь]

КТО ЧТО СКАЗАЛ:
[по каждому участнику, кто высказался — очень коротко, 1 строка на
человека, суть его позиции/реплики, с сохранением характера]

СТОИТ ЛИ ОБРАТИТЬ ВНИМАНИЕ:
[Если из разговора реально следует что-то, на что Валику стоит
посмотреть — напиши конкретно. Если это был просто треп без ничего
практического — так и напиши: "ничего срочного, просто трепались
про X" — не выдумывай важность на пустом месте]

Пиши по-русски, тепло и живо, не формально. Общий объём — не больше
700 символов.
"""
    return await ask(client, prompt)


async def main():
    repo_hint = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ("bld-system", "bld-panel") else None

    print("Клонируем/обновляем репозитории...")
    if not await sync_repos_or_alert():
        return

    print("Ищем повод для разговора...")
    starter_role, spark_line = await find_spark(repo_hint)
    print(f"\n{ROLE_LABELS.get(starter_role, starter_role)}: {spark_line}\n{'=' * 60}")

    team = build_office_chat_team()
    workflow = build_chat_workflow(team)

    result = await workflow.run(spark_line)
    transcript = extract_messages(result.get_outputs())

    for msg in transcript:
        if msg.role == "assistant":
            label = ROLE_LABELS.get(msg.author_name or "", msg.author_name or "system")
            print(f"\n{label}: {msg.text}")

    print(f"\n{'=' * 60}\nСобираем заметку...")
    report = await compile_chat_report(starter_role, spark_line, transcript)

    print(f"\n{'=' * 60}\n{report}")
    send_telegram_report(report)


if __name__ == "__main__":
    asyncio.run(main())
