"""
Общие вспомогательные функции для всех трёх workflow (discussion,
board_meeting, office_chat) — чтобы не дублировать одно и то же в трёх
местах.
"""

from typing import Any
import json
import subprocess
from datetime import datetime
from pathlib import Path

from agent_framework import Message

STATE_DIR = Path(".state")


async def ask(client, prompt: str) -> str:
    """Одноразовый текстовый запрос к модели, без tools и без истории.

    Используется там, где не нужен полноценный Agent — просто "спросить
    и получить текстовый ответ" (формулировка темы, финальный отчёт).
    """
    response = await client.get_response([Message(role="user", contents=[prompt])])
    return response.text.strip()


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


def load_task_board(limit: int = 15) -> list[dict]:
    """Общая доска задач — видят оба отряда, чтобы не дублировать работу.
    Хранится в .state/task_board.json, коммитится в bld-team."""
    path = STATE_DIR / "task_board.json"
    if not path.exists():
        return []
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
        return board[-limit:]
    except Exception:
        return []


def save_task_board_entry(entry: dict) -> None:
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
            ["git", "commit", "-m", "chore: обновление доски задач"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[task board] Не удалось сохранить: {e}")


def load_task_board(limit: int = 15) -> list[dict]:
    """Общая доска задач всех отрядов — чтобы не дублировать работу и
    видеть, что уже сделано/в процессе/отклонено. Файл коммитится в
    репозиторий bld-team (не bld-system!), как и память тем."""
    path = STATE_DIR / "task_board.json"
    if not path.exists():
        return []
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
        return board[-limit:]
    except Exception:
        return []


def save_task_board_entry(entry: dict) -> None:
    """Добавляет запись в доску задач и коммитит обратно в репозиторий."""
    STATE_DIR.mkdir(exist_ok=True)
    path = STATE_DIR / "task_board.json"
    board = []
    if path.exists():
        try:
            board = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            board = []
    board.append(entry)
    board = board[-100:]
    path.write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", str(path)], check=True)
        result = subprocess.run(
            ["git", "commit", "-m", f"chore: доска задач — {entry.get('squad', '?')}"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[task board] Не удалось сохранить в git: {e}")


def load_task_board(limit: int = 15) -> list[dict]:
    """Общая доска задач всех отрядов — чтобы не дублировать работу и
    видеть, что уже сделано/в процессе. Хранится в .state/task_board.json,
    коммитится в репозиторий bld-team (не bld-system)."""
    path = STATE_DIR / "task_board.json"
    if not path.exists():
        return []
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
        return board[-limit:]
    except Exception:
        return []


def save_task_board_entry(entry: dict) -> None:
    """Добавляет запись на доску задач и коммитит файл обратно."""
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
            ["git", "commit", "-m", f"chore: доска задач ({entry.get('squad', '?')})"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[task board] Не удалось сохранить: {e}")


def load_task_board(limit: int = 20) -> list[dict]:
    """Читает общую доску задач отрядов — чтобы разные отряды видели,
    что уже сделано/в работе, и не дублировали друг друга."""
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
    board = load_task_board(limit=200)
    board.append(entry)
    board = board[-100:]
    path.write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", str(path)], check=True)
        result = subprocess.run(
            ["git", "commit", "-m", f"chore: доска задач — {entry.get('squad', '?')}"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[task board] Не удалось сохранить в git: {e}")


def load_task_board(limit: int = 15) -> list[dict]:
    """Читает доску задач — общий журнал того, что отряды уже делают/
    сделали, чтобы не дублировать работу друг друга."""
    path = STATE_DIR / "task_board.json"
    if not path.exists():
        return []
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
        return board[-limit:]
    except Exception:
        return []


def save_task_board_entry(entry: dict) -> None:
    """Добавляет запись в доску задач и коммитит обратно в репозиторий."""
    STATE_DIR.mkdir(exist_ok=True)
    path = STATE_DIR / "task_board.json"
    board = []
    if path.exists():
        try:
            board = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            board = []
    board.append(entry)
    board = board[-100:]
    path.write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", str(path)], check=True)
        result = subprocess.run(["git", "commit", "-m", "chore: доска задач обновлена"], capture_output=True, text=True)
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[task board] Не удалось сохранить: {e}")


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


def load_active_work(limit: int = 15) -> list[dict]:
    """Читает журнал активной/недавней работы (.state/active_work.json) —
    чтобы разные команды видели, что уже делается или недавно сделано,
    и не хватались за одно и то же одновременно."""
    path = STATE_DIR / "active_work.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))[-limit:]
    except Exception:
        return []


def record_work(squad_or_team: str, task: str, branch_name: str, status: str) -> None:
    """Записывает запись в журнал активной работы и коммитит в
    репозиторий. status: 'in_progress' | 'done' | 'rejected'."""
    from datetime import datetime

    STATE_DIR.mkdir(exist_ok=True)
    path = STATE_DIR / "active_work.json"
    entries = []
    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            entries = []
    entries.append({
        "team": squad_or_team,
        "task": task,
        "branch": branch_name,
        "status": status,
        "time": datetime.now().strftime("%d.%m.%Y %H:%M"),
    })
    entries = entries[-50:]
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", str(path)], check=True)
        result = subprocess.run(
            ["git", "commit", "-m", f"chore: журнал работы ({squad_or_team})"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[active work] Не удалось сохранить журнал в git: {e}")


def format_active_work_context(entries: list[dict]) -> str:
    """Форматирует журнал в текст для промпта — 'что уже делается/сделано'."""
    if not entries:
        return "(журнал пуст — пока никто ничего не делал)"
    lines = [f"- [{e['status']}] {e['team']}: {e['task']} (ветка {e['branch']}, {e['time']})" for e in entries]
    return "\n".join(lines)


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
    from tools.repo_tools import clone_or_update_repos, RepoSyncError
    from tools.telegram_report import send_telegram_report

    try:
        print(clone_or_update_repos())
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
    """
    history: list[Message] = [Message(role="user", contents=[opening_prompt])]
    transcript: list[Message] = []

    for i in range(max_turns):
        agent = participants[i % len(participants)]
        response = await agent.run(history)
        msg = Message(role="assistant", contents=[response.text], author_name=agent.name)
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


async def compile_brief(full_report: str, header_emoji: str = "🏁") -> str:
    """Сжимает подробный отчёт (инженерная задача/отряд) в короткий,
    в духе того, как CTO кратко резюмирует на созвоне — не бюрократический
    документ с разделами, а 5-8 строк по существу. Полная версия всё
    равно уходит в вики через curate_knowledge — здесь только то, что
    летит в Telegram."""
    from config.client_factory import get_chat_client
    from config.models import GROWTH_MODEL_ASSIGNMENTS

    client = get_chat_client(GROWTH_MODEL_ASSIGNMENTS.get("mlops_engineer", "gpt-5.4"))
    prompt = f"""
Вот подробный отчёт о технической работе:

{full_report}

Сожми до короткого отчёта в стиле "CTO кратко резюмирует на созвоне" —
5-8 строк, без бюрократических разделов и заголовков-простыней. Формат:

[что сделано, одна строка]
[кто делал / какой отряд, если релевантно]
[вердикт Review Gate одной строкой: одобрено / были замечания-исправлено / отклонено]
[ветка для мерджа]
[если что-то важное пошло не так — одна строка, иначе не пиши]

Без markdown-звёздочек, простой текст для Telegram.
"""
    return await ask(client, prompt)


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
