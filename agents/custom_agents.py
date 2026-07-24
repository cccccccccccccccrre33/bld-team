"""
Добавление и удаление участников дискуссии БЕЗ изменения Python-кода.

Добавить кого-то нового:
    1. Скопируй config/custom_agents.yaml.example в config/custom_agents.yaml
    2. Опиши агента (id, имя модели, инструкции-личность) — см. пример в файле.
    3. Просто запусти main.py снова — новый участник уже в дискуссии.

Убрать кого-то из дефолтной четвёрки (agents/team.py):
    DISABLE_ROLES=product_frontend,qa_security python main.py
    (или задай DISABLE_ROLES в .env)

Оба механизма читаются из agents/team.py::build_team() и
agents/roster.py::build_full_roster() — работают в любом workflow,
который строит команду через одну из этих функций.
"""

from __future__ import annotations

import os
from pathlib import Path

from config.client_factory import get_chat_client
from tools.repo_tools import git_diff, git_log, grep_repo, list_repo_files, read_file

_REPO_TOOLS = [list_repo_files, read_file, git_log, git_diff, grep_repo]

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "custom_agents.yaml"


def disabled_roles() -> set[str]:
    """Роли (встроенные ИЛИ кастомные), которые нужно исключить —
    DISABLE_ROLES=cto,qa_security в .env, без единой строчки кода."""
    raw = os.getenv("DISABLE_ROLES", "")
    return {r.strip() for r in raw.split(",") if r.strip()}


def load_custom_agents(default_can_read_repo: bool = True) -> dict:
    """Возвращает {role_id: Agent} для всех агентов, описанных в
    config/custom_agents.yaml. Файл — опциональный: если его нет,
    просто возвращает {} и ничего не ломает. Уважает disabled_roles()."""
    if not _CONFIG_PATH.exists():
        return {}

    try:
        import yaml
    except ImportError:
        print(
            "[custom_agents] config/custom_agents.yaml найден, но пакет "
            "PyYAML не установлен — добавь 'pyyaml' в requirements.txt "
            "(уже добавлено в этом форке) и переустанови зависимости."
        )
        return {}

    data = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    disabled = disabled_roles()
    result: dict = {}

    for spec in data.get("agents", []):
        role_id = spec.get("id")
        if not role_id:
            print("[custom_agents] Пропущен агент без 'id' в custom_agents.yaml")
            continue
        if role_id in disabled:
            continue
        instructions = spec.get("instructions", "").strip()
        if not instructions:
            print(f"[custom_agents] У агента '{role_id}' пустые instructions — пропущен")
            continue

        model_name = ""
        model_env = spec.get("model_env")
        if model_env:
            model_name = os.getenv(model_env, "")
        if not model_name:
            model_name = spec.get("model_default", "gpt-5.4-mini")

        can_read_repo = spec.get("can_read_repo", default_can_read_repo)
        tools = _REPO_TOOLS if can_read_repo else []

        try:
            agent = get_chat_client(model_name).as_agent(
                name=role_id,
                instructions=instructions,
                tools=tools,
            )
        except Exception as e:  # noqa: BLE001 — один сломанный кастомный агент не должен ронять весь запуск
            print(f"[custom_agents] Не удалось создать агента '{role_id}': {e}")
            continue

        result[role_id] = agent

    return result
