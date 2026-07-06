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
from tools.repo_tools import git_log, grep_repo, list_repo_files, read_file
from tools.telegram_report import send_telegram_report
from workflows._common import (
    ask,
    curate_knowledge,
    extract_messages,
    extract_next_step,
    load_recent_topics,
    looks_like_meta_complaint,
    save_topic,
    sync_repos_or_alert,
)
from workflows.squad_task import dispatch_squads
from agents.squads import SQUADS


def assign_task_to_squad(task: str) -> str:
    """По ключевым словам решает, какому отряду ближе задача. Если
    непонятно — по умолчанию Альфа (ядро/данные), т.к. большинство
    задач у BLD пока про сам движок/данные, а не про надёжность/security."""
    lowered = task.lower()
    for key in ("bravo", "alpha"):
        if any(kw in lowered for kw in SQUADS[key]["domain_keywords"]):
            return key
    return "alpha"

MAX_MESSAGES = 20  # достаточно для живой дискуссии, не разорительно

ROLE_LABELS = {
    "mekhmat":  "🔢 Мехмат",
    "fiztech":  "⚙️  Физтех",
    "fizmat":   "🎲 Физмат",
    "tehmat":   "♟️  Техмат",
    "chief_scientist": "🔭 Chief Scientist",
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

    recent_topics = load_recent_topics("board_topics.json")
    recent_block = ""
    if recent_topics:
        recent_block = (
            "\nПоследние темы прошлых заседаний (НЕ повторяй их и не бери "
            "тот же угол — код между заседаниями мог не измениться, но "
            "тема должна быть новой; если ничего нового не нашлось, копни "
            "глубже в другую часть кода):\n"
            + "\n".join(f"- {t}" for t in recent_topics)
        )

    client = get_chat_client(BOARD_MODEL_ASSIGNMENTS["agenda_setter"])
    agenda_agent = client.as_agent(
        name="agenda_setter",
        instructions="Формулируешь техническую повестку для совета директоров на основе реального кода.",
        tools=AGENDA_TOOLS,
    )
    prompt = f"""
{COMPANY_CONTEXT}
{AGENDA_SCOPE}
{recent_block}

Загляни в реальный код (git_log, grep_repo, read_file по bld-system и
bld-panel), найди что-то конкретное, за что можно зацепиться, и сам
сформулируй ОДИН острый вопрос для заседания совета — какой сочтёшь
наиболее актуальным именно сейчас, глядя на реальное состояние кода.
Не подгоняй под шаблон — тема должна родиться из того, что ты реально
увидел в коде.
Ответь ТОЛЬКО самим вопросом, без преамбулы и кавычек.
"""
    response = await agenda_agent.run(prompt)
    topic = response.text.strip()
    save_topic("board_topics.json", topic)
    return topic


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
    """Составляет ПОЛНЫЙ отчёт с детальной стенограммой — кто что сказал,
    а не сжатое резюме на 2 строки."""
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

Реальная стенограмма заседания совета директоров:
{steno}

Составь ПОДРОБНЫЙ отчёт для Валика (без markdown-звёздочек, простой
текст для Telegram, сообщение может быть разбито на части — не бойся
объёма, детальность важнее краткости):

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
СОВЕТ ДИРЕКТОРОВ — {now}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ВОПРОС:
[одна-две строки]

ХОД ОБСУЖДЕНИЯ:
[Это главная часть — реально по каждой значимой реплике: РОЛЬ — что
именно сказал, какой аргумент привёл, с кем спорил и почему. Не сжимай
в одну строку на человека — если Мехмат привёл конкретный формальный
аргумент, опиши именно его; если Физтех возразил конкретной цифрой или
ограничением — укажи какой. Сохраняй характер и резкость реплик, не
сглаживай разногласия. Это должно читаться как реальный отчёт о
дискуссии, а не как аннотация к ней.]

ГДЕ СОШЛИСЬ / ГДЕ РАЗОШЛИСЬ:
[Явно укажи: в чём было согласие, и в чём остался нерешённый спор
(если остался) — не делай вид, что все обязательно пришли к консенсусу.
ВАЖНО: если Chief Scientist выразил фундаментальные сомнения в самой
постановке задачи (а не просто в деталях реализации) — это должно быть
явно и заметно здесь, а не потеряно среди прочих реплик. Его роль
именно в том, чтобы ловить "решаем не ту задачу" — если он это сказал,
Валик должен это увидеть отчётливо, даже если остальные не согласны.]

РЕКОМЕНДАЦИЯ:
[итоговая рекомендация, 2-4 строки, конкретно]

СЛЕДУЮЩИЙ ШАГ:
[один конкретный, выполнимый одним человеком за разумный срок шаг]

Пиши по-русски, детально и конкретно — Валик должен реально понимать,
кто что говорил и почему, а не только итог.
"""
    return await ask(secretary_client, prompt)


async def main():
    cli_hint = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None

    print("Синхронизация репозиториев...")
    if not await sync_repos_or_alert():
        return

    print("Формулируем повестку заседания...")
    agenda = await find_agenda(cli_hint)
    print(f"\nПовестка:\n{agenda}\n")
    print("=" * 80)

    board = build_board()
    workflow = build_board_workflow(board)

    result = await workflow.run(agenda)
    transcript = extract_messages(result.get_outputs())
    assistant_messages = [m for m in transcript if m.role == "assistant"]

    if not assistant_messages:
        alert = (
            "⚠️ ЗАСЕДАНИЕ НЕ ДАЛО РЕПЛИК — сессия отменена\n\n"
            f"Тема: {agenda}\n\n"
            "GroupChat вернул пустую стенограмму (0 сообщений участников). "
            "Дальше по пайплайну идти нет смысла — отчёт и инженерная задача "
            "не запускаются. Следующее заседание пройдёт по расписанию как обычно."
        )
        print(alert)
        send_telegram_report(alert)
        return

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

    # Инженерная команда реально пишет и коммитит код по "следующему
    # шагу" — в отдельную ветку, Валик сам ревьюит и мержит.
    print("\n" + "=" * 80)
    print("Определяем задачу для инженерной команды...")
    secretary_client = get_chat_client(BOARD_MODEL_ASSIGNMENTS["secretary"])
    task = await extract_next_step(report, secretary_client)
    print(f"Задача: {task}")

    if looks_like_meta_complaint(task):
        alert = (
            "⚠️ ЗАДАЧА ДЛЯ ИНЖЕНЕРНОЙ КОМАНДЫ ВЫГЛЯДИТ НЕОСМЫСЛЕННОЙ — пропущена\n\n"
            f"Извлечённый 'следующий шаг': {task}\n\n"
            "Похоже на жалобу модели на нехватку данных, а не на реальную "
            "задачу (например, отчёт заседания получился пустым/битым). "
            "Инженерная команда НЕ запущена — реализовывать тут нечего."
        )
        print(alert)
        send_telegram_report(alert)
        return

    target_squad = assign_task_to_squad(task)
    other_squad = "bravo" if target_squad == "alpha" else "alpha"
    tasks_by_squad = {target_squad: task, other_squad: None}  # второй отряд сам найдёт себе задачу

    print(f"Задача уходит в {SQUADS[target_squad]['label']}; "
          f"{SQUADS[other_squad]['label']} параллельно ищет свою проблему...")
    squad_reports = await dispatch_squads(tasks_by_squad)

    for squad_report in squad_reports:
        print(f"\n{squad_report}")
        send_telegram_report(squad_report)
        await curate_knowledge("Совет директоров / Инженерный отряд", report + "\n\n" + squad_report)


if __name__ == "__main__":
    asyncio.run(main())
