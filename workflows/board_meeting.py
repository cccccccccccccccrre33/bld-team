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

from agents.board import build_board, COMPANY_CONTEXT
from config.client_factory import get_chat_client
from config.models import BOARD_MODEL_ASSIGNMENTS
from tools.repo_tools import git_log, grep_repo, list_repo_files, read_file
from tools.telegram_report import send_telegram_report
from workflows._common import (
    run_free_conversation,
    ask,
    compile_brief,
    curate_knowledge,
    extract_messages,
    extract_next_step,
    load_recent_topics,
    load_rotation_turn,
    looks_like_meta_complaint,
    save_rotation_turn,
    save_topic,
    sync_repos_or_alert,
)
from workflows.squad_initiative import run_squad_initiative
from workflows.squad_task import dispatch_squads, run_squad_relay, run_squad_task, task_spans_both_domains
from workflows.task_board import (
    MAX_CONCURRENT,
    add_task as board_add_task,
    get_active_tasks,
    update_task_status as board_update_task_status,
)
from agents.squads import SQUADS


def assign_task_to_squad(task: str) -> str:
    """По ключевым словам решает, какому отряду ближе задача. Порядок
    проверки — от самых специфичных зон к самой общей: QA/тестирование
    (qra), anomaly-движок/trust scoring (anomaly), понимание языка
    (nlu), security/надёжность (bravo), инфраструктура (platform),
    интерфейс (product), и только затем ядро/данные (alpha) — она же
    финальный fallback, т.к. большинство задач у BLD пока про сам
    движок/данные и это самая широкая по ключевым словам зона."""
    lowered = task.lower()
    for key in ("qra", "anomaly", "nlu", "bravo", "platform", "product", "alpha"):
        if any(kw in lowered for kw in SQUADS[key]["domain_keywords"]):
            return key
    return "alpha"



ROLE_LABELS = {
    "mekhmat":  "🔢 Мехмат",
    "fiztech":  "⚙️  Физтех",
    "fizmat":   "🎲 Физмат",
    "tehmat":   "♟️  Техмат",
    "chief_scientist": "🔭 Chief Scientist",
    "ceo": "👑 CEO",
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


MAX_ROUNDS = 4  # каждый из 5 участников говорит примерно по 4 раза


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
Валик должен это увидеть отчётливо, даже если остальные не согласны.
ТАКЖЕ ВАЖНО: если CEO высказался (он вмешивается редко, только когда
совет фундаментально расходится) — его слово финальное, вынеси его
отдельной явной строкой "СЛОВО CEO:", а не растворяй среди прочих
реплик.]

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
    participants = list(board.values())

    try:
        transcript = await run_free_conversation(
            participants, agenda, max_turns=MAX_ROUNDS * len(participants)
        )
        assistant_messages = [m for m in transcript if m.role == "assistant"]
    except Exception as e:
        print(f"Обсуждение упало с ошибкой: {e}")
        transcript = []
        assistant_messages = []

    if not assistant_messages:
        alert = (
            "⚠️ ОБСУЖДЕНИЕ НЕ СОСТОЯЛОСЬ (баг оркестрации GroupChat), "
            "но тема конкретная — передаём её напрямую в инженерную работу, "
            "минуя протокол заседания.\n\n"
            f"Тема: {agenda}"
        )
        print(alert)
        send_telegram_report(alert)

        # Тема уже сформулирована agenda_setter'ом с реальным доступом к
        # коду — она сама по себе достаточно конкретна, чтобы стать
        # инженерной задачей, даже если групповое обсуждение не удалось.
        # Не выбрасываем хорошую тему только из-за сбоя в discussion-слое.
        if task_spans_both_domains(agenda):
            print("Тема затрагивает обе зоны — отряды работают эстафетой...")
            relay_report = await run_squad_relay(agenda)
            brief = await compile_brief(relay_report)
            send_telegram_report(brief)
            await curate_knowledge("Совет директоров (без обсуждения) / Эстафета", relay_report)
        else:
            target_squad = assign_task_to_squad(agenda)
            print(f"Тема уходит напрямую в {SQUADS[target_squad]['label']}...")
            squad_reports = await dispatch_squads({target_squad: agenda})
            for squad_report in squad_reports:
                brief = await compile_brief(squad_report)
                send_telegram_report(brief)
                await curate_knowledge("Совет директоров (без обсуждения) / Инженерный отряд", squad_report)
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

    brief = await compile_brief(report, context_hint="заседание совета директоров")
    send_telegram_report(brief)

    # Инженерная команда реально пишет и коммитит код по "следующему
    # шагу" — в отдельную ветку; мерж в main теперь автоматический через
    # Review Gate (см. workflows/engineering_task.py), без основателя.
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

    if task_spans_both_domains(task):
        print("Задача затрагивает обе зоны — отряды работают эстафетой на одной ветке...")
        # РАНЬШЕ эта задача вообще не попадала на общую доску задач —
        # workflows/task_board.py её не видел, а значит MAX_CONCURRENT и
        # проверка дублей по всей компании были неполными (учитывали
        # только Squad/Individual Initiative, но не совет директоров).
        relay_task_id = board_add_task(
            task, "relay:alpha+bravo", status="in_progress",
            reason="Совместная задача обеих зон — извлечена как 'следующий шаг' заседания совета директоров.",
        )
        try:
            relay_report = await run_squad_relay(task)
            board_update_task_status(relay_task_id, "done")
        except Exception as e:
            board_update_task_status(relay_task_id, "rejected", f"Упало с необработанным исключением: {e}")
            relay_report = (
                f"❌ ЭСТАФЕТА ОТРЯДОВ ПО ИТОГАМ СОВЕТА ДИРЕКТОРОВ УПАЛА С ОШИБКОЙ\n\n"
                f"Задача: {task}\n\nОшибка: {e}"
            )
        print(f"\n{relay_report}")
        send_telegram_report(relay_report)
        await curate_knowledge("Совет директоров / Эстафета отрядов", report + "\n\n" + relay_report)
        return

    target_squad = assign_task_to_squad(task)
    all_squad_keys = list(SQUADS.keys())
    idle_squads = [k for k in all_squad_keys if k != target_squad]

    # Задача совета директоров — стратегический приоритет: всегда
    # регистрируется и выполняется, независимо от загрузки (в отличие
    # от простаивающих отрядов ниже, которые сами ищут себе работу
    # оппортунистически и потому честно ждут своей очереди при нехватке
    # места). Регистрируем СРАЗУ — это резервирует один слот ёмкости
    # ДО того, как считаем, сколько свободно для простаивающих отрядов.
    task_id = board_add_task(
        task, target_squad, status="in_progress",
        reason="Извлечено как 'следующий шаг' из заседания совета директоров.",
    )
    print(f"Задача уходит в {SQUADS[target_squad]['label']} (зарегистрирована на доске: {task_id})...")

    # РАНЬШЕ: максимум ОДИН дополнительный отряд, и только через раз —
    # то есть при 4 отрядах трое почти никогда не работали параллельно
    # с целевым, хотя реальный потолок параллелизма (MAX_CONCURRENT в
    # workflows/task_board.py) почти всегда позволял больше. Это и
    # создавало ощущение "имитации бурной деятельности" вместо живой
    # параллельной экосистемы.
    #
    # ТЕПЕРЬ: считаем реально свободную ёмкость (по всей компании, не
    # только по этому заседанию) и даём шанс ВСЕМ простаивающим отрядам
    # по очереди, по честной ротации приоритета (чтобы не всегда
    # доставалось одному и тому же порядку, если слотов на всех не
    # хватает) — вместо жёсткого потолка "1 через раз".
    turn = load_rotation_turn("squad_idle_rotation")
    offset = (turn % len(idle_squads)) if idle_squads else 0
    rotated_idle = idle_squads[offset:] + idle_squads[:offset]
    save_rotation_turn("squad_idle_rotation", turn + 1)

    free_slots = max(0, MAX_CONCURRENT - len(get_active_tasks()))
    activated_idle = rotated_idle[:free_slots]

    async def _run_target() -> str:
        try:
            rep = await run_squad_task(target_squad, task)
            board_update_task_status(task_id, "done")
            return rep
        except Exception as e:
            board_update_task_status(task_id, "rejected", f"Упало с необработанным исключением: {e}")
            return (
                f"❌ ИНЖЕНЕРНАЯ ЗАДАЧА ОТ СОВЕТА ДИРЕКТОРОВ УПАЛА С ОШИБКОЙ\n\n"
                f"Отряд: {SQUADS[target_squad]['label']}\nЗадача: {task}\n\nОшибка: {e}"
            )

    coros = [_run_target()]
    if activated_idle:
        print(f"Свободно слотов: {free_slots} (из {MAX_CONCURRENT}). По ротации сами ищут "
              f"себе задачу параллельно: {', '.join(SQUADS[k]['label'] for k in activated_idle)}...")
        # run_squad_initiative уже полностью самодостаточен: сканирует
        # свою зону, проверяет дубли на доске, различает мелкие правки
        # от рискованных (тогда идёт через CTO), сам обновляет доску,
        # шлёт свой отчёт в Telegram и пишет в вики — здесь не нужно
        # повторять эту логику, только дождаться завершения.
        coros.extend(run_squad_initiative(k) for k in activated_idle)
    else:
        print(f"Свободных слотов для простаивающих отрядов сейчас нет (заняты {len(get_active_tasks())} "
              f"из {MAX_CONCURRENT}) — они отдыхают этот цикл, а не потому что их искусственно придержали.")

    results = await asyncio.gather(*coros)
    main_report = results[0]  # run_squad_initiative ничего не возвращает — отчитывается сама

    print(f"\n{main_report}")
    send_telegram_report(main_report)
    await curate_knowledge("Совет директоров / Инженерный отряд", report + "\n\n" + main_report)


if __name__ == "__main__":
    asyncio.run(main())
