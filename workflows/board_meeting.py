"""
Заседание совета директоров.

В отличие от workflows/discussion.py (код-ревью, привязано к коммитам),
здесь никакого доступа к репозиториям нет. Сценарий:

1. Определяем повестку — либо из аргумента командной строки
   (python main_board.py "тема"), либо агент agenda_setter сам
   формулирует стратегический вопрос на основе контекста компании.
2. GroupChat: mekhmat, fiztech, fizmat, tehmat обсуждают вопрос под
   управлением секретаря (кто говорит следующим).
3. По окончании секретарь сжимает всю дискуссию в короткий структурированный
   отчёт (проблема -> позиции -> итоговая рекомендация -> следующий шаг).
4. Отчёт печатается в консоль и отправляется в Telegram.
"""

import asyncio
import sys

from agent_framework import ChatMessage
from agent_framework.workflows import GroupChatBuilder

from agents.board import build_board, COMPANY_CONTEXT
from config.client_factory import get_chat_client
from config.models import BOARD_MODEL_ASSIGNMENTS
from tools.telegram_report import send_telegram_report

MAX_MESSAGES = 16  # заседание короче код-ревью — тут не нужно копать код

DEFAULT_AGENDA_HINTS = """
Примеры вопросов, если нужно предложить свой (не обязательно брать
буквально один из них — сформулируй наиболее актуальный сейчас):
- Стоит ли сузить фокус до одного проекта (скорее всего BLD) или
  осознанно вести три параллельно ещё какое-то время.
- Как получить первого платящего клиента BLD в следующие 4-6 недель.
- Когда и на каких условиях имеет смысл искать сооснователя или
  первого сотрудника, при том что сейчас компания — один человек.
- Bootstrapped-рост vs привлечение инвестиций на этой стадии.
- Что из трёх проектов стоит заморозить/закрыть, если ресурс не резиновый.
"""


async def find_agenda(cli_hint: str | None) -> str:
    """Формулирует тему заседания. Если передан аргумент командной строки —
    использует его как есть. Иначе агент сам предлагает актуальный вопрос."""
    if cli_hint:
        return cli_hint.strip()

    agenda_client = get_chat_client(BOARD_MODEL_ASSIGNMENTS["agenda_setter"])
    prompt = f"""
{COMPANY_CONTEXT}
{DEFAULT_AGENDA_HINTS}

Сформулируй ОДИН конкретный стратегический вопрос для сегодняшнего
заседания совета директоров. Вопрос должен требовать реального решения
"что делать дальше", а не быть общим ("как расти лучше").
Ответь ТОЛЬКО самим вопросом, без преамбулы.
"""
    response = await agenda_client.get_response([ChatMessage(role="user", text=prompt)])
    return response.text.strip()


def build_board_workflow(board: dict):
    secretary_client = get_chat_client(BOARD_MODEL_ASSIGNMENTS["secretary"])

    def stop_condition(messages: list[ChatMessage]) -> bool:
        assistant_messages = [m for m in messages if m.role == "assistant"]
        return len(assistant_messages) >= MAX_MESSAGES

    workflow = (
        GroupChatBuilder()
        .set_prompt_based_manager(
            chat_client=secretary_client,
            display_name="secretary",
            instructions="""
Ты — секретарь заседания совета директоров. У тебя нет своего мнения
о стратегии, твоя задача — после каждого сообщения решать, кто из
участников (mekhmat, fiztech, fizmat, tehmat) должен ответить следующим.

Правила выбора:
- Если кого-то явно упомянули по имени/роли — выбирай его.
- Если кто-то задал прямой вопрос — выбирай адресата.
- Если прозвучало утверждение, которое противоречит складу мышления
  другого участника (например: чистый расчёт без учёта реакции рынка,
  или план без учёта ограничения по времени одного человека) — дай
  ему слово, чтобы возразить.
- Не давай одному участнику говорить три раза подряд без необходимости.
- Если обсуждение пришло к согласию или четырём участникам нечего
  больше добавить — заверши заседание.
""",
        )
        .participants(**board)
        .termination_condition(stop_condition)
        .build()
    )
    return workflow


async def compile_report(agenda: str, transcript: list[ChatMessage]) -> str:
    """Сжимает всю дискуссию в короткий отчёт, пригодный для Telegram."""
    secretary_client = get_chat_client(BOARD_MODEL_ASSIGNMENTS["secretary"])

    discussion_text = "\n".join(
        f"{m.author_name or 'unknown'}: {m.text}" for m in transcript if m.role == "assistant"
    )

    prompt = f"""
Вопрос заседания: {agenda}

Стенограмма заседания совета директоров:
{discussion_text}

Составь короткий отчёт для Валика (основателя) по итогам этого заседания.
Формат строго такой (используй именно эти заголовки, без markdown-звёздочек,
это уйдёт в Telegram обычным текстом):

ВОПРОС:
(одна строка)

ПОЗИЦИИ:
(2-4 строки — кто на чём настаивал, коротко, только суть разногласий)

РЕКОМЕНДАЦИЯ:
(итоговая рекомендация совета, 2-4 строки, конкретно)

СЛЕДУЮЩИЙ ШАГ:
(один конкретный, выполнимый одним человеком за разумный срок шаг)

Пиши по-русски, кратко, без воды. Общий объём — не больше 900 символов.
"""
    response = await secretary_client.get_response([ChatMessage(role="user", text=prompt)])
    return response.text.strip()


async def main():
    cli_hint = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None

    print("Формулируем повестку заседания...")
    agenda = await find_agenda(cli_hint)
    print(f"\nПовестка:\n{agenda}\n")
    print("=" * 80)

    board = build_board()
    workflow = build_board_workflow(board)

    transcript: list[ChatMessage] = []
    events = await workflow.run(agenda, stream=True)
    async for event in events:
        if hasattr(event, "data") and isinstance(event.data, ChatMessage):
            msg = event.data
            transcript.append(msg)
            print(f"\n[{msg.author_name or 'system'}]: {msg.text}")

    print("\n" + "=" * 80)
    print("Готовим отчёт...")
    report = await compile_report(agenda, transcript)

    print("\n" + "=" * 80)
    print("ОТЧЁТ:\n")
    print(report)

    send_telegram_report(report)


if __name__ == "__main__":
    asyncio.run(main())
