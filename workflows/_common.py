"""
Общие вспомогательные функции для всех трёх workflow (discussion,
board_meeting, office_chat) — чтобы не дублировать одно и то же в трёх
местах.
"""

from typing import Any
import asyncio
import json
import subprocess
from datetime import datetime
from pathlib import Path

from agent_framework import Message

from tools.telegram_report import send_telegram_report

STATE_DIR = Path(".state")


async def ask(client, prompt: str) -> str:
    """Одноразовый текстовый запрос к модели, без tools и без истории.

    Используется там, где не нужен полноценный Agent — просто "спросить
    и получить текстовый ответ" (формулировка темы, финальный отчёт).

    С ретраями (см. safe_agent_run ниже) — та же причина: сторонние
    модели через Foundry иногда падают с 'no healthy upstream'
    (транзиентная недоступность бэкенда), и это не повод ронять весь
    воркфлоу.
    """
    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = await client.get_response([Message(role="user", contents=[prompt])])
            return response.text.strip()
        except Exception as e:
            if attempt == RETRY_ATTEMPTS - 1:
                raise
            print(f"[ask] Попытка {attempt + 1}/{RETRY_ATTEMPTS} упала ({e}), жду {RETRY_DELAY_SECONDS}с...")
            await asyncio.sleep(RETRY_DELAY_SECONDS)


# Сколько раз пробуем один и тот же вызов, прежде чем сдаться. Причина
# появления: "no healthy upstream" от Azure Foundry на сторонних
# моделях (DeepSeek/Llama/Mistral/grok/Kimi и т.п.) — это транзиентная
# недоступность конкретного бэкенда, в большинстве случаев проходит
# через несколько секунд. Раньше НИ ОДИН вызов person.run()/ask() в
# воркфлоу на полном ростере (build_full_roster, ~612 человек) не был
# защищён вообще — единственный неудачный вызов ронял весь скрипт
# (main_company_pulse.py и т.п.) с необработанным исключением. Теперь,
# когда добрая половина ростера — сторонние модели с ограниченной
# квотой, вероятность попасть на "минутную недоступность" не нулевая,
# и должна гаситься здесь, а не крашить весь GitHub Actions run.
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 5.0


async def safe_agent_run(person, prompt: str, person_label: str = "") -> str | None:
    """Обёртка над person.run(prompt) с ретраями и graceful-провалом.

    Если модель конкретного агента временно недоступна ('no healthy
    upstream' и подобные транзиентные ошибки инфраструктуры) — пробует
    ещё RETRY_ATTEMPTS-1 раз с паузой RETRY_DELAY_SECONDS. Если так и
    не получилось — печатает ЧЁТКОЕ сообщение с указанием, КТО именно
    упал (person_label), чтобы это было видно в логах GitHub Actions, и
    возвращает None вместо падения всего воркфлоу. Вызывающий код
    должен уметь пропустить этот шаг (например, выбрать другого
    человека или просто не породить сообщение в этом тике) — не
    считать None крашем.

    Если один и тот же person_label падает ПОСТОЯННО (не время от
    времени) — это, вероятно, НЕ транзиентная проблема, а модель,
    которая либо не задеплоена под этим именем в Foundry, либо
    задеплоена неправильно — тогда ретраи не помогут, и это надо чинить
    руками (проверить имя деплоя в config/models.py против реального
    списка деплоев в Azure AI Foundry).
    """
    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = await person.run(prompt)
            return response.text.strip()
        except Exception as e:
            if attempt == RETRY_ATTEMPTS - 1:
                print(
                    f"[safe_agent_run] {person_label or '?'} — модель недоступна после "
                    f"{RETRY_ATTEMPTS} попыток, пропускаем этот шаг (не крашим воркфлоу). "
                    f"Если это повторяется ПОСТОЯННО именно для {person_label or '?'} — "
                    f"проверь, что соответствующий deployment name реально существует в "
                    f"Azure AI Foundry (см. config/models.py). Ошибка: {e}"
                )
                return None
            print(
                f"[safe_agent_run] {person_label or '?'}: попытка {attempt + 1}/{RETRY_ATTEMPTS} "
                f"упала ({e}), жду {RETRY_DELAY_SECONDS}с..."
            )
            await asyncio.sleep(RETRY_DELAY_SECONDS)


def extract_messages(outputs: list[Any]) -> list[Message]:
    """Разворачивает результат workflow.run(...).get_outputs() в плоский
    список Message.

    GroupChatBuilder может вернуть outputs как плоский список Message,
    так и вложенные списки (в зависимости от output_from) — эта функция
    одинаково корректно обрабатывает оба варианта, чтобы не гадать
    заранее какой именно вернёт конкретная версия SDK.
    """
    result: list[Message] = []
    for item in outputs:
        if isinstance(item, Message):
            result.append(item)
        elif isinstance(item, (list, tuple)):
            result.extend(extract_messages(item))
    return result


def load_recent_topics(state_file: str, limit: int = 8) -> list[str]:
    """Читает последние темы заседаний из файла в самом репозитории
    bld-team (не bld-system!) — простая "память", чтобы не повторяться.
    Если файла ещё нет — возвращает пустой список."""
    path = STATE_DIR / state_file
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data[-limit:]
    except Exception:
        return []


# ПРИМЕЧАНИЕ: здесь раньше было ПЯТЬ практически идентичных
# определений load_task_board()/save_task_board_entry(), одно за
# другим (в Python реально работало только последнее — предыдущие
# были чистым мёртвым кодом, оставшимся от предыдущих правок, которые
# дописывали новую версию функции, но не удаляли старую). Хуже того:
# они читали/писали .state/task_board.json как ПРОСТОЙ СПИСОК, тогда
# как настоящая, реально используемая доска задач — workflows/
# task_board.py — хранит там СЛОВАРЬ {"tasks": [...], "last_updated":
# ...}. Единственный код, который импортировал версии отсюда (а не из
# workflows/task_board.py), был мёртвый run_squad_autonomous_cycle в
# squad_task.py (см. комментарий там же) — если бы его когда-нибудь
# вызвали, он тихо переписал бы файл в несовместимый формат и уронил
# бы чтение доски во всей остальной компании. Удалено целиком —
# канонический источник правды один: workflows/task_board.py.


def load_rotation_turn(key: str) -> int:
    """Читает текущий 'ход' ротации (0 или 1) из .state/{key}.json —
    используется чтобы простаивающий отряд не искал себе задачу КАЖДЫЙ
    раз (это и создавало риск постоянного шума от несвязанных
    параллельных веток), а только через раз."""
    path = STATE_DIR / f"{key}.json"
    if not path.exists():
        return 0
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("turn", 0)
    except Exception:
        return 0


def save_rotation_turn(key: str, turn: int) -> None:
    """Сохраняет 'ход' ротации и коммитит обратно в репозиторий bld-team."""
    STATE_DIR.mkdir(exist_ok=True)
    path = STATE_DIR / f"{key}.json"
    path.write_text(json.dumps({"turn": turn}), encoding="utf-8")

    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", str(path)], check=True)
        result = subprocess.run(
            ["git", "commit", "-m", f"chore: ротация ({key})"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[rotation] Не удалось сохранить ротацию в git: {e}")


def save_topic(state_file: str, topic: str) -> None:
    """Дописывает тему в файл памяти и коммитит его обратно в репозиторий
    bld-team (использует git-креды, уже настроенные actions/checkout).
    Если коммит/пуш не удался (например, локальный запуск без git-репо
    с правами на пуш) — просто печатает предупреждение, не падает."""
    STATE_DIR.mkdir(exist_ok=True)
    path = STATE_DIR / state_file
    topics = []
    if path.exists():
        try:
            topics = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            topics = []
    topics.append(topic)
    topics = topics[-30:]  # не растим файл бесконечно
    path.write_text(json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", str(path)], check=True)
        result = subprocess.run(
            ["git", "commit", "-m", f"chore: обновлена память тем ({state_file})"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[topic memory] Не удалось сохранить тему в git: {e}")


async def sync_repos_or_alert() -> bool:
    """Синхронизирует bld-system/bld-panel перед началом сессии.

    Раньше clone_or_update_repos() при провале клонирования просто
    печатала текст ошибки и работа продолжалась с уже сломанными tools
    (агенты получали 'путь не найден' на ровном месте, без объяснения
    причины). Теперь при сбое:
    1) сырая git-ошибка сразу летит в Telegram, а не тонет в логах Actions;
    2) сессия (заседание/чат/лаба) не запускается вслепую поверх
       наполовину доступного кода.

    Возвращает True, если можно продолжать, False - если нужно прервать
    workflow прямо здесь (вызывающий код должен сделать `return`).
    """
    from tools.repo_tools import REPOS, WORKDIR, clone_or_update_repos, RepoSyncError
    from tools.telegram_report import send_telegram_report

    try:
        print(clone_or_update_repos())
        try:
            from tools.context_builder import ensure_company_context
            ensure_company_context(REPOS, WORKDIR)
        except Exception as e:  # noqa: BLE001 — контекст опционален, не должен ронять сессию
            print(f"[context_builder] Пропущено: {e}")
        return True
    except RepoSyncError as e:
        alert = (
            "⚠️ РЕПОЗИТОРИИ НЕДОСТУПНЫ — сессия отменена\n\n"
            f"{e}\n\n"
            "Обсуждать код, который не виден, нет смысла — эта сессия "
            "пропущена, следующая запустится по расписанию как обычно."
        )
        print(alert)
        send_telegram_report(alert)
        return False


async def run_free_conversation(
    participants: list,
    opening_prompt: str,
    max_turns: int = 8,
) -> list[Message]:
    """Простой поочерёдный обмен репликами между 2-3 участниками.

    Без оркестратора/модератора — для маленьких групп (пара/тройка)
    это надёжнее, чем GroupChatBuilder, и не требует лишней модели на
    роль модератора. Каждый участник видит полную историю разговора
    (клиент по умолчанию stateless, поэтому историю передаём явно
    каждый раз).

    Порядок ходов — простой round-robin по списку participants.

    Каждый ход защищён safe_agent_run — если у конкретного участника
    модель временно недоступна, этот ход просто пропускается (без
    сообщения), разговор продолжается со следующего участника, вместо
    падения всей функции.
    """
    history: list[Message] = [Message(role="user", contents=[opening_prompt])]
    transcript: list[Message] = []

    for i in range(max_turns):
        agent = participants[i % len(participants)]
        text = await safe_agent_run(agent, history, person_label=getattr(agent, "name", f"participant_{i % len(participants)}"))
        if text is None:
            continue
        msg = Message(role="assistant", contents=[text], author_name=agent.name)
        history.append(msg)
        transcript.append(msg)

    return transcript


async def extract_next_step(report_text: str, client) -> str:
    """Достаёт чистую формулировку 'следующего шага' из уже готового
    отчёта — независимо от конкретного форматирования отчёта."""
    prompt = f"""
Вот отчёт с заседания:

{report_text}

Выдели ТОЛЬКО "следующий шаг"/задачу для исполнения — одним
предложением, без заголовка, без лишних слов, только сама задача
как есть.
"""
    return await ask(client, prompt)


# Фразы-маркеры того, что отчёт/задача на самом деле не осмысленная
# постановка, а мета-жалоба модели на нехватку данных (например, когда
# стенограмма пришла пустой/повреждённой). Если это проскочило в
# "следующий шаг" — нельзя нести это инженерной команде, она честно
# попытается это "реализовать" (см. инцидент с ложной веткой в
# bld-system, где лид-инженер добавил в бота классификатор интентов,
# реагирующий на просьбу прислать стенограмму — вместо реальной фичи).
_META_COMPLAINT_MARKERS = [
    "пришлите", "пришли текст", "нет стенограммы", "нет самой стенограммы",
    "у меня нет", "нет данных для", "не хватает данных", "отсутствует стенограмма",
    "нет реальных реплик", "нет текста стенограммы",
]


def load_task_board(limit: int = 15) -> list[dict]:
    """Общая доска задач — чтобы отряды видели, что уже делается/сделано,
    и не дублировали работу друг друга."""
    path = STATE_DIR / "task_board.json"
    if not path.exists():
        return []
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
        return board[-limit:]
    except Exception:
        return []


def save_task_board_entry(entry: dict) -> None:
    """Дописывает запись в доску задач и коммитит обратно в bld-team."""
    STATE_DIR.mkdir(exist_ok=True)
    path = STATE_DIR / "task_board.json"
    board = []
    if path.exists():
        try:
            board = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            board = []
    board.append(entry)
    board = board[-50:]
    path.write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", str(path)], check=True)
        result = subprocess.run(
            ["git", "commit", "-m", "chore: доска задач обновлена"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[task board] Не удалось сохранить доску в git: {e}")


def looks_like_meta_complaint(text: str) -> bool:
    """True, если текст похож на жалобу модели ('пришлите стенограмму'),
    а не на реальную постановку задачи."""
    lowered = text.lower()
    return any(marker in lowered for marker in _META_COMPLAINT_MARKERS)


async def dispatch_worker(task: str, model_name: str, project_context: str) -> str:
    """"Нанимает" одного специалиста под конкретную задачу — свежий Agent
    с реальным доступом к коду (bld-system, bld-panel), который реально
    разбирается в задаче и пишет подробный текстовый отчёт: что выяснил,
    что делать и почему. НИКОГДА не пишет код — только текст и выводы,
    Валик сам решает, реализовывать предложение или нет."""
    from config.client_factory import get_chat_client
    from tools.repo_tools import git_diff, git_log, grep_repo, list_repo_files, read_file

    client = get_chat_client(model_name)
    worker = client.as_agent(
        name="worker",
        instructions=f"""
Тебя только что "наняли" на конкретную задачу, которую поставило
заседание (совет директоров или правление). {project_context}

Твоя задача — РЕАЛЬНО разобраться и написать подробный текстовый отчёт:
что ты выяснил, что конкретно нужно сделать и почему именно так, какие
есть варианты и их плюсы/минусы, с чего начать на практике.

У тебя есть tools для доступа к реальному коду (list_repo_files,
read_file, git_log, git_diff, grep_repo) — используй их, ЕСЛИ задача
касается кода/архитектуры. Если задача организационная/бизнесовая
(наём, метрики, процессы) — код не при чём, рассуждай по существу
задачи, не притягивай код искусственно.

ВАЖНО: НИКОГДА не пиши код, патчи или диффы — только текст, выводы и
конкретные рекомендации. Валик сам решит, писать ли код по твоим
рекомендациям. Пиши по-русски, по делу, структурированно, но не
разводи воду — если задача простая, не усложняй искусственно.
""",
        tools=[list_repo_files, read_file, git_log, git_diff, grep_repo],
    )
    response = await worker.run(f"Твоя задача: {task}\n\nРазберись в реальном коде и напиши отчёт.")
    return response.text.strip()


def notify_done(title: str, note: str = "") -> None:
    """Отчёт о РЕАЛЬНО готовой работе — ноль LLM-вызовов, просто
    название и (опционально) короткая пометка. Раньше здесь стоял
    compile_brief() — отдельный вызов модели ТОЛЬКО ради того, чтобы
    сжать уже готовый текст до 4-6 строк для Telegram. По прямому
    запросу Валика ('не тратить токены ещё и на отчёты') — это лишний
    расход: если само событие простое (задача сделана/отклонена/
    упала), сжимать реально нечего, а если сложное — подробности и так
    целиком уходят в вики через curate_knowledge(), которую никто не
    отменял. Telegram получает только факт, не пересказ хода мысли."""
    text = f"✅ {title.strip()}"
    if note:
        text += f" — {note.strip()[:200]}"
    send_telegram_report(text)


def notify_failed(title: str, reason: str = "") -> None:
    """То же самое, но для сбоев — это НЕ шум обсуждений, а сигнал,
    что что-то реально сломалось и стоит внимания, поэтому остаётся
    (в отличие от промежуточных вердиктов/статусов — см. комментарий
    в вызывающих местах, почему их убрали из Telegram вовсе)."""
    text = f"❌ {title.strip()}"
    if reason:
        text += f": {reason.strip()[:200]}"
    send_telegram_report(text)


async def curate_knowledge(source_label: str, content: str) -> None:
    """Knowledge Curator — редкий гибрид: инженер, который добровольно
    ведёт вики компании. После каждого значимого события (заседание,
    инженерная задача, лаборатория) добавляет ОДНУ короткую запись в
    постоянную базу знаний (.state/company_wiki.md) — что решено и
    почему, без пересказа всей дискуссии. Дешёвая модель, чистая
    суммаризация — цель не решать, а фиксировать уже решённое, чтобы
    через полгода можно было понять, почему систему сделали именно так.

    Как и save_topic(), коммитит файл обратно в репозиторий bld-team.
    Если коммит/пуш не удался — печатает предупреждение, не падает.
    """
    from config.client_factory import get_chat_client
    from config.models import KNOWLEDGE_CURATOR_MODEL

    client = get_chat_client(KNOWLEDGE_CURATOR_MODEL)
    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    prompt = f"""
Вот результат события "{source_label}" от {now}:

{content}

Составь ОДНУ короткую запись для постоянной базы знаний компании —
markdown, 3-5 строк, без вступлений и воды. Формат СТРОГО такой:

### {source_label} — {now}
- Решение/находка: [одна строка по существу]
- Причина: [одна строка — почему именно так]
- Открытый вопрос/риск: [одна строка, если есть; если нет — не пиши эту строку вообще]
"""
    entry = await ask(client, prompt)

    STATE_DIR.mkdir(exist_ok=True)
    wiki_path = STATE_DIR / "company_wiki.md"
    existing = wiki_path.read_text(encoding="utf-8") if wiki_path.exists() else "# Вики компании BLD\n"
    wiki_path.write_text(existing.rstrip() + "\n\n" + entry.strip() + "\n", encoding="utf-8")

    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", str(wiki_path)], check=True)
        result = subprocess.run(
            ["git", "commit", "-m", f"docs: вики — {source_label}"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[knowledge curator] Не удалось сохранить вики в git: {e}")


# --- Личный дневник (для молодых специалистов, agents/global_geniuses.py
# и agents/expansion_geniuses.py) — .state/notebooks/{name}.json.
#
# Идея: "студенческая погружённость" — человек не просто раз в
# несколько дней случайно всплывает с идеей, а ведёт непрерывную нить
# любопытства, которую сам же читает в начале следующей сессии ("в
# прошлый раз я копал в сторону X, продолжу оттуда"). Даже если сессия
# не привела к конкретному предложению — запись всё равно делается
# ("посмотрел туда-то, пока не нашёл ничего конкретного, но кажется
# перспективным X") — именно это и создаёт ощущение постоянной
# вовлечённости, а не серии несвязанных случайных вспышек.

NOTEBOOKS_DIR = STATE_DIR / "notebooks"


def load_notebook(name: str, limit: int = 5) -> list[dict]:
    """Последние записи личного дневника человека. Пустой список, если
    дневника ещё нет (первая сессия)."""
    path = NOTEBOOKS_DIR / f"{name}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data[-limit:]
    except Exception:
        return []


def format_notebook(entries: list[dict]) -> str:
    if not entries:
        return "(это твоя первая запись в личном дневнике — начинай с чистого листа)"
    return "\n".join(f"[{e['date']}] {e['entry']}" for e in entries)


def save_notebook_entry(name: str, entry: str) -> None:
    """Дописывает запись в личный дневник и коммитит в репозиторий
    bld-team — тот же паттерн, что и вики/доска задач."""
    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    path = NOTEBOOKS_DIR / f"{name}.json"
    entries = []
    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            entries = []
    entries.append({"date": datetime.now().strftime("%d.%m %H:%M"), "entry": entry})
    entries = entries[-40:]  # не растим бесконечно
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", str(path)], check=True)
        result = subprocess.run(
            ["git", "commit", "-m", f"chore: дневник — {name}"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[notebook] Не удалось сохранить дневник {name} в git: {e}")


# --- Справедливое участие — .state/participation.json ---
#
# Раньше каждый механизм (Company Pulse, Chevruta, Individual
# Initiative, Лаборатория, HR) выбирал людей ЧИСТО случайно и
# независимо друг от друга. На практике за день это давало заметный
# перекос: кто-то попадался несколько раз, кто-то — ни разу, просто по
# случайности. Единый трекер участия (общий для ВСЕХ механизмов —
# ключ по имени, а не по механизму) позволяет каждому пикеру слегка
# смещать вероятность в пользу тех, кто дольше всех молчал — без
# жёсткой детерминированной очереди (это выглядело бы механически),
# просто честный наклон вероятности.

PARTICIPATION_PATH = STATE_DIR / "participation.json"


def _load_participation() -> dict:
    if not PARTICIPATION_PATH.exists():
        return {}
    try:
        return json.loads(PARTICIPATION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def record_participation(*names: str) -> None:
    """Отмечает, что эти люди только что где-то поучаствовали (сказали
    реплику, взяли инициативу и т.п.) — вызывается из ЛЮБОГО механизма
    (Pulse/Chevruta/Individual Initiative/Lab/HR), не только из одного
    места, чтобы трекер был честным по всей компании сразу."""
    data = _load_participation()
    now = datetime.now().isoformat()
    for name in names:
        data[name] = now
    STATE_DIR.mkdir(exist_ok=True)
    PARTICIPATION_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", str(PARTICIPATION_PATH)], check=True)
        result = subprocess.run(
            ["git", "commit", "-m", "chore: участие — обновлён трекер"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[participation] Не удалось сохранить трекер в git: {e}")


def fair_sample(pool: list[str], k: int = 1, fairness: float = 0.6) -> list[str]:
    """Выбирает k человек из pool со смещением в пользу тех, кто дольше
    всех не участвовал НИГДЕ в компании (по общему трекеру). Не жёсткая
    очередь — fairness (0..1) задаёт силу смещения: 0 = чистая
    случайность, 1 = почти детерминированная ротация по давности.
    По умолчанию 0.6 — заметный наклон, но не механический.

    Люди, которых ещё вообще не было в трекере (никогда не участвовали),
    получают максимальный приоритет — как самые "давно молчавшие"."""
    import random as _random

    data = _load_participation()
    now = datetime.now()

    def staleness(name: str) -> float:
        ts = data.get(name)
        if not ts:
            return 1e9  # никогда не участвовал — максимальный приоритет
        try:
            last = datetime.fromisoformat(ts)
            return (now - last).total_seconds()
        except Exception:
            return 1e9

    staleness_values = {n: staleness(n) for n in pool}
    max_stale = max(staleness_values.values()) or 1.0

    weights = []
    for n in pool:
        fairness_weight = staleness_values[n] / max_stale  # 0..1, больше = давно не участвовал
        random_weight = _random.random()
        weights.append(fairness * fairness_weight + (1 - fairness) * random_weight + 0.01)

    k = min(k, len(pool))
    chosen: list[str] = []
    remaining = list(pool)
    remaining_weights = list(weights)
    for _ in range(k):
        total = sum(remaining_weights)
        r = _random.uniform(0, total)
        upto = 0.0
        for i, w in enumerate(remaining_weights):
            upto += w
            if upto >= r:
                chosen.append(remaining.pop(i))
                remaining_weights.pop(i)
                break
    return chosen
