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

from agent_framework import Message
from agent_framework.orchestrations import GroupChatBuilder

from agents.board import build_board, COMPANY_CONTEXT
from config.client_factory import get_chat_client
from config.models import BOARD_MODEL_ASSIGNMENTS
from tools.repo_tools import clone_or_update_repos, git_log, grep_repo, list_repo_files, read_file
from tools.telegram_report import send_telegram_report
from workflows._common import ask, extract_messages

MAX_MESSAGES = 20  # достаточно для живой дискуссии, не разорительно

ROLE_LABELS = {
    "mekhmat":  "🔢 Мехмат",
    "fiztech":  "⚙️  Физтех",
    "fizmat":   "🎲 Физмат",
    "tehmat":   "♟️  Техмат",
    "secretary": "📋 Секретарь",
}

AGENDA_TOOLS = [list_repo_files, read_file, git_log, grep_repo]

AGENDA_SCOPE = """
Про зону обсуждения: Совет директоров — в первую очередь техническое
обсуждение по проекту BLD System (оба репозитория: bld-system и
bld-panel) — архитектура, надёжность, anomaly detection engine,
качество кода, технический долг, готовность к росту нагрузки.

Тему выбираешь ты сам, свободно — глядя в реальный код, а не по
шаблону. Если в процессе всплывает деловой угол (например: "это
техническое решение упирается в то, что мы пока не знаем реальных
объёмов данных от клиентов" или "эта надёжность системы важна именно
потому что от неё зависит доверие первого клиента") — это нормально,
можно затронуть, но по-настоящему деловые темы (продажи, цены,
приоритеты между BLD/Хвилей/Нейробаристой, привлечение инвестиций)
не должны становиться ГЛАВНОЙ темой заседания — для этого есть
отдельный орган, Правление. Изредка такой угол уместен как часть
технического разговора, но не как самоцель.
"""


async def find_agenda(cli_hint: str | None) -> str:
    if cli_hint:
        return cli_hint.strip()

    client = get_chat_client(BOARD_MODEL_ASSIGNMENTS["agenda_setter"])
    agenda_agent = client.as_agent(
        name="agenda_setter",
        instructions="Формулируешь техническую повестку для совета директоров на основе реального кода.",
        tools=AGENDA_TOOLS,
    )
    prompt = f"""
{COMPANY_CONTEXT}
{AGENDA_SCOPE}

Загляни в реальный код (git_log, grep_repo, read_file по bld-system и
bld-panel), найди что-то конкретное, за что можно зацепиться, и сам
сформулируй ОДИН острый вопрос для заседания совета — какой сочтёшь
наиболее актуальным именно сейчас, глядя на реальное состояние кода.
Не подгоняй под шаблон — тема должна родиться из того, что ты реально
увидел в коде.
Ответь ТОЛЬКО самим вопросом, без преамбулы и кавычек.
"""
    response = await agenda_agent.run(prompt)
    return response.text.strip()


def build_board_workflow(board: dict):
    secretary_client = get_chat_client(BOARD_MODEL_ASSIGNMENTS["secretary"])
    secretary_agent = secretary_client.as_agent(
        name="secretary",
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
    """Сжимает всю дискуссию в короткий отчёт, пригодный для Telegram."""
    secretary_client = get_chat_client(BOARD_MODEL_ASSIGNMENTS["secretary"])

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

Стенограмма заседания совета директоров:
{steno}

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
    return await ask(secretary_client, prompt)


async def main():
    cli_hint = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None

    print("Синхронизация репозиториев...")
    print(clone_or_update_repos())

    print("Формулируем повестку заседания...")
    agenda = await find_agenda(cli_hint)
    print(f"\nПовестка:\n{agenda}\n")
    print("=" * 80)

    board = build_board()
    workflow = build_board_workflow(board)

    result = await workflow.run(agenda)
    transcript = extract_messages(result.get_outputs())

    for msg in transcript:
        if msg.role == "assistant":
            label = ROLE_LABELS.get(msg.author_name or "", msg.author_name or "system")
            print(f"\n{label}: {msg.text}")

    print("\n" + "=" * 80)
    print("Готовим отчёт...")
    report = await compile_report(agenda, transcript)

    print("\n" + "=" * 80)
    print("ОТЧЁТ:\n")
    print(report)

    send_telegram_report(report)


if __name__ == "__main__":
    asyncio.run(main())
