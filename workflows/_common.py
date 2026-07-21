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
# воркфлоу на полном ростере (build_full_roster, ~209 человек) не был
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


async def compile_brief(full_report: str, header_emoji: str = "🏁", context_hint: str = "") -> str:
