"""
Заседание совета директоров — автономный режим.

Сценарий:
1. agenda_setter сам формулирует стратегический вопрос (или берёт из CLI).
2. GroupChat: mekhmat, fiztech, fizmat, tehmat спорят.
3. Секретарь составляет ПОЛНЫЙ красивый отчёт со стенограммой —
   не краткое резюме, а живой документ где виден характер каждого.
4. Отчёт уходит в Telegram (несколькими сообщениями если длинный).
"""

import asyncio
import sys
from datetime import datetime

from agent_framework import ChatMessage
from agent_framework.workflows import GroupChatBuilder

from agents.board import build_board, COMPANY_CONTEXT
from config.client_factory import get_chat_client
from config.models import BOARD_MODEL_ASSIGNMENTS
from tools.telegram_report import send_telegram_report

MAX_MESSAGES = 20  # достаточно для живой дискуссии, не разорительно

ROLE_LABELS = {
    "mekhmat":  "🔢 Мехмат",
    "fiztech":  "⚙️  Физтех",
    "fizmat":   "🎲 Физмат",
    "tehmat":   "♟️  Техмат",
    "secretary": "📋 Секретарь",
}

DEFAULT_AGENDA_HINTS = """
Примеры направлений (выбери или придумай актуальнее):
- Как получить первого платящего клиента BLD в ближайшие 4-6 недель.
- Стоит ли вести три проекта параллельно или сузить фокус до одного.
- Когда и на каких условиях искать сооснователя — и нужен ли он вообще.
- Bootstrapped-рост vs внешние инвестиции на текущей стадии.
- Что заморозить/закрыть если ресурс (время одного человека) не резиновый.
- Как выстроить воронку продаж BLD не имея отдела продаж.
- Правильная ли ценовая модель BLD для украинского рынка прямо сейчас.
"""


async def find_agenda(cli_hint: str | None) -> str:
    if cli_hint:
        return cli_hint.strip()

    client = get_chat_client(BOARD_MODEL_ASSIGNMENTS["agenda_setter"])
    prompt = f"""
{COMPANY_CONTEXT}
{DEFAULT_AGENDA_HINTS}

Сформулируй ОДИН острый стратегический вопрос для заседания совета.
Вопрос должен быть конкретным и требовать реального решения прямо сейчас,
а не абстрактным рассуждением о будущем.
Ответь ТОЛЬКО самим вопросом, без преамбулы и кавычек.
"""
    r = await client.get_response([ChatMessage(role="user", text=prompt)])
    return r.text.strip()


def build_board_workflow(board: dict):
    secretary_client = get_chat_client(BOARD_MODEL_ASSIGNMENTS["secretary"])

    def stop_condition(messages: list[ChatMessage]) -> bool:
        return len([m for m in messages if m.role == "assistant"]) >= MAX_MESSAGES

    return (
        GroupChatBuilder()
        .set_prompt_based_manager(
            chat_client=secretary_client,
            display_name="secretary",
            instructions="""
Ты — секретарь заседания. Нет своего мнения о стратегии.
После каждого сообщения выбираешь кто говорит следующим:
mekhmat, fiztech, fizmat или tehmat.

Правила:
- Назвали кого-то по имени/роли → его очередь.
- Прямой вопрос → адресату.
- Утверждение противоречит чужой области → дай возразить.
- Один и тот же не говорит трижды подряд без необходимости.
- Пришли к выводу или нечего добавить → заверши.
""",
        )
        .participants(**board)
        .termination_condition(stop_condition)
        .build()
    )


async def compile_report(agenda: str, transcript: list[ChatMessage]) -> str:
    """Составляет полный живой отчёт — стенограмма + аналитика секретаря."""
    client = get_chat_client(BOARD_MODEL_ASSIGNMENTS["secretary"])

    # Форматируем стенограмму с метками ролей
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
Ты — секретарь, составляешь протокол заседания совета директоров для Валика.

Вопрос заседания: {agenda}
Дата и время: {now}

Стенограмма:
{steno}

Составь протокол в следующем формате (строго, без markdown звёздочек и решёток,
только сам текст — это уйдёт в Telegram):

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ПРОТОКОЛ ЗАСЕДАНИЯ СОВЕТА
{now}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ВОПРОС:
[вопрос повестки одной строкой]

СТЕНОГРАММА:
[Здесь перепиши каждую реплику в формате:
РОЛЬ — ключевая мысль реплики (1-2 предложения, сохраняя характер и интонацию
человека, не сглаживай — мехмат должен звучать дотошно и жёстко,
физтех — системно и про ресурсы, физмат — про вероятности и риски,
техмат — про игроков рынка и стимулы). Если была острая реплика — не смягчай.]

ИТОГ ДИСКУССИИ:
[3-5 предложений: в чём сошлись, в чём остались разногласия, какова
общая позиция совета]

РЕКОМЕНДАЦИЯ:
[Конкретное решение или направление — без воды, 2-3 предложения]

СЛЕДУЮЩИЙ ШАГ:
[Один действие, выполнимое одним человеком в течение недели, очень конкретно]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Пиши по-русски. Стенограмму не сокращай сильно — Валик должен чувствовать
характер каждого участника, это не краткое резюме а живой документ.
"""
    r = await client.get_response([ChatMessage(role="user", text=prompt)])
    return r.text.strip()


async def main():
    cli_hint = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None

    print("Формулируем повестку...")
    agenda = await find_agenda(cli_hint)
    print(f"\nПовестка: {agenda}\n{'=' * 60}")

    board = build_board()
    workflow = build_board_workflow(board)

    transcript: list[ChatMessage] = []
    events = await workflow.run(agenda, stream=True)
    async for event in events:
        if hasattr(event, "data") and isinstance(event.data, ChatMessage):
            msg = event.data
            transcript.append(msg)
            label = ROLE_LABELS.get(msg.author_name or "", msg.author_name or "system")
            print(f"\n{label}: {msg.text}")

    print(f"\n{'=' * 60}\nСоставляем протокол...")
    report = await compile_report(agenda, transcript)

    print(f"\n{'=' * 60}\n{report}")
    send_telegram_report(report)


if __name__ == "__main__":
    asyncio.run(main())
