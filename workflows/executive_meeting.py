"""
Заседание правления — бизнес-сторона компании.

Сценарий:
1. agenda_setter формулирует бизнес-вопрос (или берётся из CLI).
2. GroupChat: sales, marketing, cfo, hr, legal, coo — 6 разных голов,
   специально сделаны конфликтующими по мышлению.
3. Секретарь составляет протокол со стенограммой (кто что сказал,
   сохраняя характер), плюс итог и следующий шаг.
4. Отчёт уходит в Telegram.
"""

import asyncio
import sys
from datetime import datetime

from agent_framework import Message
from agent_framework.orchestrations import GroupChatBuilder

from agents.executive_board import build_executive_board, COMPANY_CONTEXT
from config.client_factory import get_chat_client
from config.models import EXEC_MODEL_ASSIGNMENTS
from tools.telegram_report import send_telegram_report
from workflows._common import ask, extract_messages

MAX_MESSAGES = 20

ROLE_LABELS = {
    "coo": "🗂️  COO",
    "hr": "🧑‍🤝‍🧑 HR",
    "secretary": "📋 Секретарь",
}

DEFAULT_AGENDA_HINTS = """
Примеры направлений (выбери или придумай актуальнее):
- Нужен ли первый наём и кого нанимать в первую очередь.
- Какие метрики стоит начать отслеживать прямо сейчас, чтобы понимать
  прогресс BLD System.
- Как выстроить процессы так, чтобы Валик не выгорел, ведя три проекта
  одновременно.
- Что из трёх проектов стоит заморозить, если ресурс не резиновый.
"""


async def find_agenda(cli_hint: str | None) -> str:
    if cli_hint:
        return cli_hint.strip()

    client = get_chat_client(EXEC_MODEL_ASSIGNMENTS["agenda_setter"])
    prompt = f"""
{COMPANY_CONTEXT}
{DEFAULT_AGENDA_HINTS}

Сформулируй ОДИН острый бизнес-вопрос для заседания правления. Вопрос
должен требовать реального решения сейчас, не общих рассуждений о
будущем. Ответь ТОЛЬКО самим вопросом, без преамбулы и кавычек.
"""
    return await ask(client, prompt)


def build_executive_workflow(board: dict):
    secretary_client = get_chat_client(EXEC_MODEL_ASSIGNMENTS["secretary"])
    secretary_agent = secretary_client.as_agent(
        name="secretary",
        instructions="""
Ты — секретарь заседания правления. Нет своего мнения о бизнесе, твоя
задача — после каждого сообщения решать, кто из участников (sales,
marketing, cfo, hr, legal, coo) должен ответить следующим.

Правила:
- Кого-то упомянули по имени/роли → его очередь.
- Прямой вопрос → адресату.
- Утверждение вне зоны компетенции говорящего, но в зоне другого
  участника → дай ему возразить/поправить.
- Не давай одному говорить трижды подряд без необходимости.
- Обсуждение исчерпано или пришли к выводу → заверши.
""",
    )

    def stop_condition(messages: list[Message]) -> bool:
        return len([m for m in messages if m.role == "assistant"]) >= MAX_MESSAGES

    return (
        GroupChatBuilder(
            participants=list(board.values()),
            orchestrator_agent=secretary_agent,
            termination_condition=stop_condition,
        )
        .build()
    )


async def compile_report(agenda: str, transcript: list[Message]) -> str:
    secretary_client = get_chat_client(EXEC_MODEL_ASSIGNMENTS["secretary"])

    lines = []
    for m in transcript:
        if m.role != "assistant":
            continue
        name = m.author_name or "unknown"
        label = ROLE_LABELS.get(name, name.upper())
        lines.append(f"{label}:\n{m.text.strip()}")
    steno = "\n\n".join(lines)

    now = datetime.now().strftime("%d.%m.%Y, %H:%M")

    prompt = f"""
Вопрос заседания: {agenda}
Дата и время: {now}

Стенограмма заседания правления:
{steno}

Составь протокол для Валика (без markdown-звёздочек, простой текст
для Telegram):

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ЗАСЕДАНИЕ ПРАВЛЕНИЯ
{now}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ВОПРОС:
[одна строка]

СТЕНОГРАММА:
[Кратко по каждому реально высказавшемуся участнику: РОЛЬ — суть его
позиции (1-2 предложения), сохраняя характер и не сглаживая разногласия]

ИТОГ:
[3-5 предложений — в чём сошлись, в чём разногласия, общая позиция]

РЕКОМЕНДАЦИЯ:
[конкретное решение, 2-3 предложения]

СЛЕДУЮЩИЙ ШАГ:
[одно конкретное действие на неделю]

Пиши по-русски, без воды. Общий объём — не больше 900 символов.
"""
    return await ask(secretary_client, prompt)


async def main():
    cli_hint = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None

    print("Формулируем повестку правления...")
    agenda = await find_agenda(cli_hint)
    print(f"\nПовестка:\n{agenda}\n{'=' * 80}")

    board = build_executive_board()
    workflow = build_executive_workflow(board)

    result = await workflow.run(agenda)
    transcript = extract_messages(result.get_outputs())

    for msg in transcript:
        if msg.role == "assistant":
            label = ROLE_LABELS.get(msg.author_name or "", msg.author_name or "system")
            print(f"\n{label}: {msg.text}")

    print(f"\n{'=' * 80}\nГотовим отчёт...")
    report = await compile_report(agenda, transcript)

    print(f"\n{'=' * 80}\n{report}")
    send_telegram_report(report)


if __name__ == "__main__":
    asyncio.run(main())
