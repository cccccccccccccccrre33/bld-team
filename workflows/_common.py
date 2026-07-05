"""
Общие вспомогательные функции для всех трёх workflow (discussion,
board_meeting, office_chat) — чтобы не дублировать одно и то же в трёх
местах.
"""

from typing import Any
import json
import subprocess
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
