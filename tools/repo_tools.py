"""
Tools для работы с приватными GitHub-репозиториями.

Репозитории клонируются один раз при старте (clone_or_update_repos),
дальше все агенты читают их с локального диска через эти функции.
Используется GitHub Personal Access Token (classic, scope: repo)
из переменной окружения GITHUB_TOKEN.

ВАЖНО: эти функции — обычные Python-функции с docstring и type hints.
Agent Framework сам строит из них function-tool схему (как и
function calling в OpenAI/Anthropic SDK) — просто передай функцию
в список tools агента, оборачивать в декораторы не обязательно.
"""

import os
import subprocess
from pathlib import Path

WORKDIR = Path(os.getenv("AI_TEAM_WORKDIR", "./repos")).resolve()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

REPOS = {
    "bld-system": "github.com/cccccccccccccccrre33/bld-system.git",
    "bld-panel": "github.com/cccccccccccccccrre33/bld-panel.git",
}

# Расширения, которые реально стоит отдавать модели как текст.
# Бинарники, lock-файлы и node_modules/venv агентам ни к чему.
TEXT_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".yml", ".yaml",
    ".toml", ".cfg", ".ini", ".sql", ".env.example", ".txt", ".sh",
}
IGNORE_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}


def _repo_path(repo_name: str) -> Path:
    if repo_name not in REPOS:
        raise ValueError(f"Неизвестный репозиторий: {repo_name}. Доступны: {list(REPOS)}")
    return WORKDIR / repo_name


def clone_or_update_repos() -> str:
    """Клонирует оба репозитория (если их ещё нет локально) или делает
    git pull (если уже клонированы). Вызывается один раз при старте
    программы, не является tool для агентов."""
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN не задан в окружении.")
    WORKDIR.mkdir(parents=True, exist_ok=True)
    results = []
    for name, repo_url in REPOS.items():
        path = WORKDIR / name
        auth_url = f"https://{GITHUB_TOKEN}@{repo_url}"
        if path.exists():
            out = subprocess.run(
                ["git", "-C", str(path), "pull", "--ff-only"],
                capture_output=True, text=True,
            )
        else:
            out = subprocess.run(
                ["git", "clone", auth_url, str(path)],
                capture_output=True, text=True,
            )
        results.append(f"{name}: {out.stdout.strip() or out.stderr.strip()}")
    return "\n".join(results)


def list_repo_files(repo_name: str, subpath: str = ".") -> str:
    """Список файлов и папок в репозитории по указанному подпути.

    Args:
        repo_name: 'bld-system' или 'bld-panel'.
        subpath: относительный путь внутри репозитория, '.' для корня.
    """
    base = _repo_path(repo_name) / subpath
    if not base.exists():
        return f"Путь не найден: {subpath}"
    lines = []
    for item in sorted(base.iterdir()):
        if item.name in IGNORE_DIRS:
            continue
        marker = "/" if item.is_dir() else ""
        lines.append(f"{item.name}{marker}")
    return "\n".join(lines) or "(пусто)"


def read_file(repo_name: str, file_path: str, max_chars: int = 8000) -> str:
    """Читает содержимое файла из репозитория.

    Args:
        repo_name: 'bld-system' или 'bld-panel'.
        file_path: путь к файлу относительно корня репозитория.
        max_chars: ограничение на размер вывода (защита контекста).
    """
    full_path = _repo_path(repo_name) / file_path
    if not full_path.exists() or not full_path.is_file():
        return f"Файл не найден: {file_path}"
    if full_path.suffix not in TEXT_EXTENSIONS:
        return f"Файл {file_path} не текстовый/не поддерживается для чтения."
    text = full_path.read_text(errors="ignore")
    if len(text) > max_chars:
        return text[:max_chars] + f"\n...[обрезано, всего {len(text)} символов]"
    return text


def git_log(repo_name: str, limit: int = 20) -> str:
    """Возвращает последние коммиты репозитория (hash, автор, дата, сообщение).

    Args:
        repo_name: 'bld-system' или 'bld-panel'.
        limit: сколько последних коммитов вернуть.
    """
    path = _repo_path(repo_name)
    out = subprocess.run(
        ["git", "-C", str(path), "log", f"-{limit}",
         "--pretty=format:%h | %ad | %an | %s", "--date=short"],
        capture_output=True, text=True,
    )
    return out.stdout or out.stderr


def git_diff(repo_name: str, commit_hash: str) -> str:
    """Показывает diff конкретного коммита.

    Args:
        repo_name: 'bld-system' или 'bld-panel'.
        commit_hash: хэш коммита (можно короткий, из git_log).
    """
    path = _repo_path(repo_name)
    out = subprocess.run(
        ["git", "-C", str(path), "show", commit_hash, "--stat", "-p"],
        capture_output=True, text=True,
    )
    diff = out.stdout or out.stderr
    if len(diff) > 6000:
        return diff[:6000] + "\n...[diff обрезан]"
    return diff


def grep_repo(repo_name: str, pattern: str, file_glob: str = "*") -> str:
    """Ищет текстовый паттерн по всему репозиторию (аналог grep -r).

    Args:
        repo_name: 'bld-system' или 'bld-panel'.
        pattern: строка или regex для поиска.
        file_glob: маска файлов, например '*.py'.
    """
    path = _repo_path(repo_name)
    out = subprocess.run(
        ["git", "-C", str(path), "grep", "-n", "-I", pattern, "--", file_glob],
        capture_output=True, text=True,
    )
    result = out.stdout or "(совпадений не найдено)"
    if len(result) > 5000:
        return result[:5000] + "\n...[результат обрезан]"
    return result
