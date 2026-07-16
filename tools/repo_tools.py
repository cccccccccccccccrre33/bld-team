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


class RepoSyncError(RuntimeError):
    """Хотя бы один репозиторий не удалось склонировать/обновить.
    Содержит человекочитаемую сводку по каждому упавшему репо."""


def clone_or_update_repos() -> str:
    """Клонирует оба репозитория (если их ещё нет локально) или делает
    git pull (если уже клонированы). Вызывается один раз при старте
    программы, не является tool для агентов.

    ВАЖНО: если клонирование/пулл хотя бы одного репозитория падает
    (returncode != 0), эта функция бросает RepoSyncError с сырым текстом
    git-ошибки. Раньше ошибка просто складывалась в текст лога и работа
    продолжалась как ни в чём не бывало — из-за этого агенты получали
    рабочую директорию без репозитория и не понимали, что происходит.
    """
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN не задан в окружении.")
    WORKDIR.mkdir(parents=True, exist_ok=True)
    results = []
    failures = []
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
        # Токен никогда не попадает в message - берём только stdout/stderr git,
        # а не auth_url.
        message = out.stdout.strip() or out.stderr.strip() or "OK"
        results.append(f"{name}: {message}")
        if out.returncode != 0:
            failures.append(f"{name}: {message}")

    summary = "\n".join(results)
    if failures:
        raise RepoSyncError(
            summary
            + "\n\nПроверь: 1) репозиторий существует под этим именем на GitHub; "
              "2) GITHUB_TOKEN/BLD_REPOS_PAT имеет доступ именно к этому репо "
              "(для fine-grained PAT — он должен быть явно выбран в списке "
              "разрешённых репозиториев, а не просто 'Contents: Read/Write')."
        )
    return summary


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


# ============================================================
# Write-инструменты — используются ТОЛЬКО инженерной командой
# (agents/engineering.py), НЕ советом директоров/код-ревью
# командой (у тех сознательно нет доступа к записи).
# Работают всегда в отдельной ветке — прямой пуш в main запрещён
# на уровне commit_and_push (см. проверку ниже).
# ============================================================

PROTECTED_BRANCHES = {"main", "master"}

# Единая постоянная ветка для ВСЕХ изменений от AI-команды — по запросу
# Валика: раньше каждая задача создавала свою уникальную ветку
# (ai-eng/<slug>-<timestamp>), из-за чего веток становилось много и
# часть терялась из виду. Теперь ВСЁ уходит в одну и ту же ветку в
# каждом репозитории (bld-system и bld-panel). Раньше отсюда Валик сам
# смотрел и мержил в main вручную; теперь (см. merge_branch_to_main
# ниже и workflows/engineering_task.py/squad_task.py) это делает Review
# Gate автоматически при чистом вердикте — Валик из этой цепочки убран
# полностью, разве что для инцидентов, где Review Gate сам не смог
# домержить (конфликт) или дважды не пропустил код — тогда решение
# уходит CTO, не основателю. create_branch() идемпотентна —
# повторные вызовы просто переключаются на существующую ветку, не
# создавая новую и не откатывая изменения.
AI_BRANCH_NAME = "bld-team-ai"


def create_branch(repo_name: str, branch_name: str, base: str = "main") -> str:
    """Создаёт новую ветку от base и переключается на неё. Использовать
    один раз в начале инженерной задачи.

    Идемпотентно: повторный вызов с тем же branch_name безопасен и не
    откатывает репозиторий на base. Раньше повторный вызов (например, если
    агент по ошибке зовёт create_branch дважды за одну задачу) сначала
    переключал репо на base, а затем 'checkout -b' падал с 'branch already
    exists' — в итоге репозиторий тихо оставался на base/main, и следующий
    write_file упирался в защиту протектед-ветки, хотя по логам задача
    была на нужной фиче-ветке.

    Args:
        repo_name: 'bld-system' или 'bld-panel'.
        branch_name: имя новой ветки, например 'ai-eng/fix-l7-thresholds'.
        base: от какой ветки создавать (обычно 'main').
    """
    path = _repo_path(repo_name)

    current = subprocess.run(
        ["git", "-C", str(path), "branch", "--show-current"],
        capture_output=True, text=True,
    ).stdout.strip()
    if current == branch_name:
        return f"Уже на ветке {branch_name} — повторный create_branch пропущен, base не трогали."

    subprocess.run(["git", "-C", str(path), "fetch", "origin", base], capture_output=True, text=True)
    subprocess.run(["git", "-C", str(path), "checkout", base], capture_output=True, text=True)
    subprocess.run(["git", "-C", str(path), "pull", "--ff-only"], capture_output=True, text=True)

    # Если ветка уже существует локально (например, задачу прервали и
    # перезапустили) - переключаемся на неё, а не пытаемся создать заново.
    exists = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--verify", "--quiet", branch_name],
        capture_output=True, text=True,
    ).returncode == 0

    if exists:
        out = subprocess.run(
            ["git", "-C", str(path), "checkout", branch_name],
            capture_output=True, text=True,
        )
    else:
        out = subprocess.run(
            ["git", "-C", str(path), "checkout", "-b", branch_name],
            capture_output=True, text=True,
        )
    return out.stdout.strip() or out.stderr.strip() or f"Ветка {branch_name} создана и активна"


def write_file(repo_name: str, file_path: str, content: str) -> str:
    """Записывает содержимое в файл репозитория (создаёт файл и папки
    при необходимости) и добавляет его в git staging (git add).
    Работает в ТЕКУЩЕЙ ветке — обязательно сначала вызови create_branch,
    иначе рискуешь записать прямо в main.

    Args:
        repo_name: 'bld-system' или 'bld-panel'.
        file_path: путь к файлу относительно корня репозитория.
        content: полное новое содержимое файла.
    """
    path = _repo_path(repo_name)

    current_branch = subprocess.run(
        ["git", "-C", str(path), "branch", "--show-current"],
        capture_output=True, text=True,
    ).stdout.strip()
    if current_branch in PROTECTED_BRANCHES:
        return (
            f"ОТКАЗ: текущая ветка '{current_branch}' защищена. "
            "Сначала вызови create_branch, чтобы создать рабочую ветку."
        )

    full_path = path / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", file_path], capture_output=True, text=True)
    return f"Записан файл {file_path} ({len(content)} символов) в ветке {current_branch}"


GTM_DIR = Path("gtm-materials")


def list_gtm_docs() -> str:
    """Список уже существующих GTM-материалов (черновики скриптов,
    сегментация рынка, письма) — чтобы отдел не дублировал то, что уже
    написано. Не имеет отношения к коду bld-system/bld-panel."""
    GTM_DIR.mkdir(exist_ok=True)
    files = sorted(p.name for p in GTM_DIR.glob("*.md"))
    return "\n".join(files) if files else "(пока пусто)"


def read_gtm_doc(file_name: str) -> str:
    """Читает существующий GTM-документ по имени файла (из list_gtm_docs)."""
    full_path = GTM_DIR / file_name
    if not full_path.exists():
        return f"Файл {file_name} не найден. Доступны: {list_gtm_docs()}"
    return full_path.read_text(encoding="utf-8")


def write_gtm_doc(file_name: str, content: str) -> str:
    """Записывает GTM-документ (markdown) в gtm-materials/ репозитория
    bld-team и коммитит его напрямую (как .state/task_board.json — это
    не код продукта, веток/PR/CTO-approval для этого не нужно).

    ВАЖНО: этот инструмент НИКОГДА не должен использоваться, чтобы
    "записать" реальную сделку, лида или контакт клиента — только
    черновики документов для последующего использования человеком.

    Args:
        file_name: имя файла, например 'sales-script-v2.md'.
        content: полное содержимое документа.
    """
    if not file_name.endswith(".md"):
        file_name += ".md"
    GTM_DIR.mkdir(exist_ok=True)
    full_path = GTM_DIR / file_name
    full_path.write_text(content, encoding="utf-8")

    subprocess.run(["git", "config", "user.name", "bld-team-gtm"], capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "bld-team-gtm@users.noreply.github.com"],
        capture_output=True, text=True,
    )
    subprocess.run(["git", "add", str(full_path)], capture_output=True, text=True)
    commit_out = subprocess.run(
        ["git", "commit", "-m", f"gtm: {file_name}"],
        capture_output=True, text=True,
    )
    if commit_out.returncode != 0 and "nothing to commit" not in commit_out.stdout:
        return f"Записан {file_name}, но коммит не удался: {commit_out.stdout}\n{commit_out.stderr}"
    push_out = subprocess.run(["git", "push"], capture_output=True, text=True)
    if push_out.returncode != 0:
        return f"Записан и закоммичен {file_name}, но push не удался: {push_out.stderr}"
    return f"Записан, закоммичен и запушен {file_name} ({len(content)} символов) в gtm-materials/"


def commit_and_push(repo_name: str, branch_name: str, commit_message: str) -> str:
    """Коммитит застейдженные изменения (после write_file) и пушит
    ветку в origin. ОТКАЗЫВАЕТ, если текущая ветка — main/master —
    прямой пуш в защищённые ветки запрещён.

    Args:
        repo_name: 'bld-system' или 'bld-panel'.
        branch_name: имя ветки, которую нужно запушить (должна уже
            быть текущей после create_branch).
        commit_message: сообщение коммита.
    """
    path = _repo_path(repo_name)

    current_branch = subprocess.run(
        ["git", "-C", str(path), "branch", "--show-current"],
        capture_output=True, text=True,
    ).stdout.strip()
    if current_branch in PROTECTED_BRANCHES:
        return f"ОТКАЗ: нельзя пушить напрямую в '{current_branch}'."

    subprocess.run(["git", "-C", str(path), "config", "user.name", "bld-team-engineer"], capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "bld-team-engineer@users.noreply.github.com"],
        capture_output=True, text=True,
    )
    commit_out = subprocess.run(
        ["git", "-C", str(path), "commit", "-m", commit_message],
        capture_output=True, text=True,
    )
    if commit_out.returncode != 0 and "nothing to commit" not in commit_out.stdout:
        return f"Ошибка коммита: {commit_out.stdout.strip() or commit_out.stderr.strip()}"

    push_out = subprocess.run(
        ["git", "-C", str(path), "push", "-u", "origin", current_branch],
        capture_output=True, text=True,
    )
    return (
        f"commit: {commit_out.stdout.strip() or '(нечего коммитить)'}\n"
        f"push: {push_out.stdout.strip() or push_out.stderr.strip()}"
    )


# ============================================================
# Мерж в main — раньше это был единственный шаг, который руками делал
# основатель ("Валик"): смотрел на ветку bld-team-ai, решал, готова ли
# она, и мержил сам. Теперь это делает Review Gate автоматически (см.
# workflows/engineering_task.py и workflows/squad_task.py): если после
# не более чем одной переделки все три ревьюера дают чистый вердикт —
# мерж происходит без участия человека. Инструмент НЕ выдаётся
# инженерам напрямую (это не write_file на минималках, это самое
# высокоставочное действие во всей системе) — вызывается только из
# самого workflow-кода после проверки вердикта, а не по решению модели.
# ============================================================


def merge_branch_to_main(repo_name: str, branch_name: str, summary: str = "") -> str:
    """Мержит указанную ветку в main и пушит main в origin.
    ОТКАЗЫВАЕТ, если branch_name сам по себе защищённая ветка (нет
    смысла мержить main в main). При конфликте мержа ОТКАТЫВАЕТ мерж
    (git merge --abort) и возвращает понятную ошибку — не оставляет
    репозиторий в конфликтном состоянии на середине операции.

    Args:
        repo_name: 'bld-system' или 'bld-panel'.
        branch_name: ветка, которую мержим в main (обычно AI_BRANCH_NAME).
        summary: короткое описание для сообщения мерж-коммита (например,
            исходная задача) — необязательно, но полезно для истории.
    """
    if branch_name in PROTECTED_BRANCHES:
        return f"ОТКАЗ: '{branch_name}' сам по себе защищённая ветка, мержить нечего."

    path = _repo_path(repo_name)

    subprocess.run(["git", "-C", str(path), "config", "user.name", "bld-team-engineer"], capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "bld-team-engineer@users.noreply.github.com"],
        capture_output=True, text=True,
    )

    subprocess.run(["git", "-C", str(path), "fetch", "origin", "main"], capture_output=True, text=True)
    checkout_out = subprocess.run(["git", "-C", str(path), "checkout", "main"], capture_output=True, text=True)
    if checkout_out.returncode != 0:
        return f"ОТКАЗ: не удалось переключиться на main: {checkout_out.stderr.strip()}"

    pull_out = subprocess.run(["git", "-C", str(path), "pull", "--ff-only"], capture_output=True, text=True)
    if pull_out.returncode != 0:
        return f"ОТКАЗ: не удалось обновить main перед мержем: {pull_out.stderr.strip()}"

    commit_msg = f"Merge {branch_name}: {summary[:100]}" if summary else f"Merge {branch_name} into main"
    merge_out = subprocess.run(
        ["git", "-C", str(path), "merge", "--no-ff", branch_name, "-m", commit_msg],
        capture_output=True, text=True,
    )
    if merge_out.returncode != 0:
        # Конфликт или другая ошибка мержа — откатываем, чтобы не
        # оставить репозиторий в conflicted-состоянии без присмотра.
        subprocess.run(["git", "-C", str(path), "merge", "--abort"], capture_output=True, text=True)
        return (
            f"ОТКАЗ: мерж {branch_name} → main не прошёл (вероятен конфликт), "
            f"мерж отменён (merge --abort), main не тронут:\n{merge_out.stdout.strip() or merge_out.stderr.strip()}\n"
            "Нужна ручная проверка — конфликт сам себя не разрешит."
        )

    push_out = subprocess.run(["git", "-C", str(path), "push", "origin", "main"], capture_output=True, text=True)
    if push_out.returncode != 0:
        return (
            f"ЧАСТИЧНЫЙ УСПЕХ: мерж сделан локально, но push в origin/main не прошёл: "
            f"{push_out.stderr.strip()}. main в этом клоне впереди origin — нужно "
            "разобраться руками, прежде чем что-то ещё пушить в main."
        )

    return f"✅ {branch_name} смержен в main и запушен в origin.\n{merge_out.stdout.strip()}"
