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

import asyncio
import contextvars
import os
import subprocess
from pathlib import Path

WORKDIR = Path(os.getenv("AI_TEAM_WORKDIR", "./repos")).resolve()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# ============================================================
# Изоляция параллельных задач по репозиторию — появилась вместе с
# переходом individual_initiative.py на параллельный запуск нескольких
# людей за один тик (см. workflows/individual_initiative.py).
#
# РАНЬШЕ у bld-system и bld-panel была ОДНА расшаренная рабочая
# директория на диске, и ВСЕ задачи писали в ОДНУ и ту же постоянную
# ветку (AI_BRANCH_NAME) — это было осознанным решением Валика в своё
# время ("не хочу, чтобы веток становилось много"), но оно физически
# не совместимо с несколькими людьми, реально пишущими код в один
# репозиторий одновременно: два процесса, переключающие и коммитящие в
# одну и ту же директорию/ветку разом — это гонка, а не просто
# неаккуратность.
#
# ТЕПЕРЬ: у каждой задачи снова СВОЯ ветка (см. slugify-генерацию в
# workflows/engineering_task.py), но живёт она в изолированной рабочей
# копии через `git worktree` (WORKTREES_DIR ниже) — отдельная
# директория на диске на отдельной ветке, при этом все worktree одного
# репозитория делят один и тот же объектный банк git (это ровно то, для
# чего worktree и придуман — параллельные чек-ауты одного репо). Ветка
# и рабочая копия удаляются автоматически сразу после успешного мержа
# (см. merge_branch_to_main) — то есть исходное желание Валика "не
# хочу, чтобы веток становилось много" выполняется само, а не ценой
# отказа от параллелизма.
#
# Из всего цикла (ветка -> write_file -> commit_and_push -> тесты ->
# review) РЕАЛЬНО общий (не per-worktree) ресурс остался только один —
# сама ветка main в общем клоне, в которую мержат. Поэтому лок ниже
# больше не держится на весь цикл задачи (это было бы избыточно и
# просто убивало бы параллелизм обратно до 1 на репозиторий) — он нужен
# ТОЛЬКО вокруг самого merge_branch_to_main, см. его использование в
# workflows/engineering_task.py и workflows/squad_task.py.
_REPO_WRITE_LOCKS: dict[str, asyncio.Lock] = {}


def get_repo_write_lock(repo_name: str) -> asyncio.Lock:
    """Лок ТОЛЬКО на сам merge_branch_to_main (checkout main -> merge ->
    push в общем клоне) — не на весь инженерный цикл. write_file/
    commit_and_push/run_test_suite безопасны параллельно сами по себе,
    потому что у каждой задачи своя изолированная git worktree-копия
    (см. create_branch ниже)."""
    lock = _REPO_WRITE_LOCKS.get(repo_name)
    if lock is None:
        lock = asyncio.Lock()
        _REPO_WRITE_LOCKS[repo_name] = lock
    return lock


# ContextVar (не обычный dict!) — у каждой asyncio.Task (в т.ч.
# созданной через asyncio.gather в individual_initiative.py) СВОЯ копия
# контекста: если задача A вызвала create_branch и это записало
# "активная worktree для bld-system = .../A" в контекст задачи A, то
# задача B, работающая параллельно с ней над тем же repo_name, эту
# запись не увидит — у неё либо нет активной worktree (ещё не звала
# create_branch), либо своя собственная. Именно это и позволяет
# write_file(repo_name=...) — БЕЗ branch_name в сигнатуре, потому что
# агентам её менять нельзя, схема тулов уже зафиксирована — понимать,
# в какую именно рабочую копию писать, не путая задачи между собой.
_ACTIVE_WORKTREE: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "_active_worktree", default={}
)


def _set_active_worktree(repo_name: str, path: "Path | None") -> None:
    mapping = dict(_ACTIVE_WORKTREE.get())
    if path is None:
        mapping.pop(repo_name, None)
    else:
        mapping[repo_name] = path
    _ACTIVE_WORKTREE.set(mapping)


def _get_active_worktree(repo_name: str):
    return _ACTIVE_WORKTREE.get().get(repo_name)


WORKTREES_DIR = WORKDIR / "_worktrees"

# Репозитории, которые наблюдает и обсуждает AI-команда — настраивается
# через TARGET_REPOS в .env, БЕЗ изменения кода. Формат:
#   TARGET_REPOS=имя1=github.com/владелец/репо1.git,имя2=github.com/владелец/репо2.git
# "Имя" — произвольный короткий идентификатор (используется как ключ
# repo_name везде в этом файле и как имя папки в ./repos). Можно указать
# один репозиторий или сколько угодно.
#
# Если TARGET_REPOS не задан — используются репозитории автора этого
# форка (bld-system/bld-panel), чтобы существующий деплой не сломался.


def _parse_target_repos(raw: str) -> dict:
    repos = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ValueError(
                f"Неверный формат TARGET_REPOS: '{pair}'. "
                "Ожидается 'имя=github.com/владелец/репо.git' "
                "через запятую для нескольких репозиториев."
            )
        name, _, url = pair.partition("=")
        repos[name.strip()] = url.strip()
    return repos


_TARGET_REPOS_RAW = os.getenv("TARGET_REPOS", "").strip()
REPOS = (
    _parse_target_repos(_TARGET_REPOS_RAW)
    if _TARGET_REPOS_RAW
    else {
        # Дефолт для тех, кто ничего не настроил в TARGET_REPOS: ai-team
        # обсуждает собственный код. Публичный репозиторий, не требует
        # GITHUB_TOKEN, работает сразу после `pip install` — честное демо
        # без привязки к чьему-либо приватному проекту.
        "ai-team": "github.com/cccccccccccccccrre33/bld-team.git",
    }
)

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


def _work_path(repo_name: str) -> Path:
    """Путь, с которым реально работают git-инструменты для этого
    репозитория В ЭТОЙ асинхронной задаче: если задача уже вызвала
    create_branch — её собственная изолированная worktree-копия (на её
    собственной ветке); иначе — общий клон, который теперь НИКОГДА не
    переключается на другую ветку и всегда остаётся на main (безопасно
    читать параллельно скольким угодно задачам сразу — до create_branch
    все инструменты чтения тоже идут через эту функцию)."""
    return _get_active_worktree(repo_name) or _repo_path(repo_name)


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
    # GITHUB_TOKEN нужен только для приватных репозиториев. Если целевой
    # проект публичный (обычный случай для форка этого проекта на чужом
    # open-source коде) — клонирование по https и без токена работает.
    WORKDIR.mkdir(parents=True, exist_ok=True)
    results = []
    failures = []
    for name, repo_url in REPOS.items():
        path = WORKDIR / name
        auth_url = f"https://{GITHUB_TOKEN}@{repo_url}" if GITHUB_TOKEN else f"https://{repo_url}"
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
            + "\n\nПроверь: 1) URL в TARGET_REPOS правильный и репозиторий "
              "существует; 2) если репозиторий приватный — GITHUB_TOKEN "
              "задан и имеет доступ именно к нему (для fine-grained PAT — "
              "он должен быть явно выбран в списке разрешённых "
              "репозиториев, а не просто 'Contents: Read/Write'). Для "
              "публичных репозиториев GITHUB_TOKEN не нужен."
        )
    return summary


def list_repo_files(repo_name: str, subpath: str = ".") -> str:
    """Список файлов и папок в репозитории по указанному подпути.

    Args:
        repo_name: 'bld-system' или 'bld-panel'.
        subpath: относительный путь внутри репозитория, '.' для корня.
    """
    base = _work_path(repo_name) / subpath
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
    full_path = _work_path(repo_name) / file_path
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
    path = _work_path(repo_name)
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
    path = _work_path(repo_name)
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
    path = _work_path(repo_name)
    out = subprocess.run(
        ["git", "-C", str(path), "grep", "-n", "-I", pattern, "--", file_glob],
        capture_output=True, text=True,
    )
    result = out.stdout or "(совпадений не найдено)"
    if len(result) > 5000:
        return result[:5000] + "\n...[результат обрезан]"
    return result


# ============================================================
# Реальный запуск тестов — НЕ мнение модели о том, сломается код или
# нет, а фактический результат pytest. До этого инструмента Review
# Gate был на 100% "читаю diff глазами и предполагаю" — даже
# Failure Engineer, чья работа "ломать систему", на самом деле только
# ПРИДУМЫВАЛ сценарии поломки текстом, ни один из них реально не
# исполнялся. Сильные модели на ревью — это хорошо, но это не замена
# классическим вещам (CI, тесты, fuzzing) — это ДОПОЛНЕНИЕ к ним. См.
# agents/review_gate.py: fuzzer теперь пишет реальные edge-case тесты,
# а эта функция реально их прогоняет.
# ============================================================


def run_test_suite(repo_name: str, test_path: str = "", timeout_seconds: int = 300) -> str:
    """Реально запускает pytest в изолированной рабочей копии этой
    задачи (см. create_branch/_work_path) и возвращает фактический
    результат: сколько тестов прошло/упало, и краткий вывод первых
    упавших.

    Это НЕ мнение модели — это детерминированный результат выполнения
    кода. Используется Review Gate'ом как объективная проверка поверх
    (не вместо) оценки ревьюеров-агентов.

    Args:
        repo_name: 'bld-system' или 'bld-panel'.
        test_path: путь к конкретному тестовому файлу/директории
            относительно корня репо (например 'tests/test_fuzz_*.py');
            пусто — запускает весь набор тестов.
        timeout_seconds: жёсткий таймаут на случай зависшего теста
            (например бесконечный цикл в сгенерированном коде) — без
            этого один плохой тест может повесить весь workflow.
    """
    path = _work_path(repo_name)
    target = str(path / test_path) if test_path else str(path)

    try:
        out = subprocess.run(
            ["python", "-m", "pytest", target, "--tb=short", "-q", "--no-header"],
            cwd=str(path),
            capture_output=True, text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return (
            f"❌ ТЕСТЫ НЕ ЗАВЕРШИЛИСЬ за {timeout_seconds}с (возможен бесконечный цикл "
            "или зависание) — считать падением, разбираться руками."
        )
    except FileNotFoundError:
        return "⚠️ pytest не найден в окружении — тесты пропущены (это не то же самое, что 'прошли')."

    output = (out.stdout or "") + (out.stderr or "")
    if len(output) > 4000:
        # Оставляем начало (обычно самое релевантное — упавшие тесты
        # перечисляются в начале вывода pytest) и хвост (summary line).
        output = output[:3000] + "\n...[обрезано]...\n" + output[-1000:]

    status = "✅ ВСЕ ТЕСТЫ ПРОШЛИ" if out.returncode == 0 else "❌ ЕСТЬ УПАВШИЕ ТЕСТЫ"
    return f"{status} (exit code {out.returncode})\n\n{output}"


# ============================================================
# Write-инструменты — используются ТОЛЬКО инженерной командой
# (agents/engineering.py), НЕ советом директоров/код-ревью
# командой (у тех сознательно нет доступа к записи).
# Работают всегда в отдельной ветке — прямой пуш в main запрещён
# на уровне commit_and_push (см. проверку ниже).
# ============================================================

PROTECTED_BRANCHES = {"main", "master"}

# ИСТОРИЯ: раньше здесь была ЕДИНАЯ постоянная ветка для всех задач
# (AI_BRANCH_NAME = "bld-team-ai") — по прошлой просьбе Валика не
# плодить много веток. Это работало, пока за раз в компании реально
# что-то писал только один человек. С переходом на параллельные
# индивидуальные инициативы (см. workflows/individual_initiative.py)
# это стало физически несовместимо с "несколько человек пишут код в
# один репозиторий одновременно": общая ветка = общая рабочая
# директория = гонка. Вернули уникальную ветку на задачу (см.
# slugify-генерацию в workflows/engineering_task.py), но проблему
# "веток становится много", ради которой была сделана консолидация,
# теперь решает автоматическая уборка: merge_branch_to_main удаляет
# ветку (и локально, и в origin) и worktree сразу после успешного
# мержа — то есть непрочитанных веток не копится, но не ценой отказа
# от параллелизма. Имя оставлено как константа для обратной
# совместимости импортов в других модулях, но больше не означает "одна
# на всех" — это просто дефолтный fallback-префикс, реально не
# используется напрямую в текущем потоке (см. branch_prefix в
# run_engineering_task).
AI_BRANCH_NAME = "bld-team-ai"


def _worktree_dir_name(branch_name: str) -> str:
    """Имя ветки может содержать '/' (например 'ai-eng/fix-l7') — как
    путь к директории это не годится, заменяем на безопасный разделитель."""
    return branch_name.replace("/", "__")


def create_branch(repo_name: str, branch_name: str, base: str = "main") -> str:
    """Создаёт новую ветку от base в СОБСТВЕННОЙ изолированной git
    worktree (не в общем клоне!) и делает её "текущей" для этой задачи
    — все дальнейшие write_file/commit_and_push/run_test_suite/read-
    инструменты этой же асинхронной задачи автоматически пойдут в неё
    (см. _work_path/_ACTIVE_WORKTREE выше). Использовать один раз в
    начале инженерной задачи.

    Общий клон (WORKDIR/repo_name) при этом НИКОГДА не переключается на
    другую ветку — он всегда остаётся на main. Это и есть та смена
    архитектуры, которая делает несколько одновременных задач на одном
    repo_name безопасными: раньше create_branch переключал ЕДИНУЮ
    расшаренную директорию на другую ветку, и вторая параллельная
    задача в этот момент читала/писала бы уже не то, что думает.

    Идемпотентно: повторный вызов с тем же branch_name в рамках той же
    задачи просто переиспользует уже созданную worktree, ничего не
    трогая.

    Args:
        repo_name: 'bld-system' или 'bld-panel'.
        branch_name: имя новой ветки, например 'ai-eng/fix-l7-thresholds'.
        base: от какой ветки создавать (обычно 'main').
    """
    shared_path = _repo_path(repo_name)
    worktree_path = WORKTREES_DIR / repo_name / _worktree_dir_name(branch_name)

    if worktree_path.exists() and _get_active_worktree(repo_name) == worktree_path:
        return f"Уже работаем в изолированной копии ветки {branch_name} — повторный create_branch пропущен."

    subprocess.run(["git", "-C", str(shared_path), "fetch", "origin", base], capture_output=True, text=True)
    WORKTREES_DIR.mkdir(parents=True, exist_ok=True)
    # prune убирает "мёртвые" записи о worktree, чья директория на диске
    # уже не существует (например, после сбойного предыдущего прогона)
    # — без этого git иногда отказывается создавать worktree с тем же
    # путём/веткой, думая, что он всё ещё занят.
    subprocess.run(["git", "-C", str(shared_path), "worktree", "prune"], capture_output=True, text=True)

    if worktree_path.exists():
        # Директория уже есть на диске (задачу перезапустили в рамках
        # того же checkout репозитория) — просто переиспользуем.
        _set_active_worktree(repo_name, worktree_path)
        return f"Изолированная копия ветки {branch_name} уже существует на диске — переиспользуем."

    branch_exists = subprocess.run(
        ["git", "-C", str(shared_path), "rev-parse", "--verify", "--quiet", branch_name],
        capture_output=True, text=True,
    ).returncode == 0

    if branch_exists:
        out = subprocess.run(
            ["git", "-C", str(shared_path), "worktree", "add", str(worktree_path), branch_name],
            capture_output=True, text=True,
        )
    else:
        out = subprocess.run(
            ["git", "-C", str(shared_path), "worktree", "add", "-b", branch_name,
             str(worktree_path), f"origin/{base}"],
            capture_output=True, text=True,
        )

    if out.returncode != 0:
        return (
            f"ОШИБКА: не удалось создать изолированную рабочую копию ветки {branch_name}: "
            f"{out.stdout.strip() or out.stderr.strip()}"
        )

    _set_active_worktree(repo_name, worktree_path)
    return out.stdout.strip() or out.stderr.strip() or f"Ветка {branch_name} создана в изолированной рабочей копии и активна"


def write_file(repo_name: str, file_path: str, content: str) -> str:
    """Записывает содержимое в файл репозитория (создаёт файл и папки
    при необходимости) и добавляет его в git staging (git add).
    Работает в изолированной рабочей копии ЭТОЙ задачи — обязательно
    сначала вызови create_branch, иначе рискуешь записать прямо в main
    (в общем клоне, который другие задачи читают параллельно).

    Args:
        repo_name: 'bld-system' или 'bld-panel'.
        file_path: путь к файлу относительно корня репозитория.
        content: полное новое содержимое файла.
    """
    path = _work_path(repo_name)

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
    """Мержит указанную ветку в main и пушит main в origin, затем
    убирает за собой: удаляет изолированную worktree-копию с диска и
    саму ветку (локально и в origin). ОТКАЗЫВАЕТ, если branch_name сам
    по себе защищённая ветка (нет смысла мержить main в main). При
    конфликте мержа ОТКАТЫВАЕТ мерж (git merge --abort) и возвращает
    понятную ошибку — не оставляет репозиторий в конфликтном состоянии
    на середине операции (и НЕ убирает worktree/ветку в этом случае —
    они остаются на диске/в origin для ручного разбора).

    ВАЖНО: вызывающий код должен держать get_repo_write_lock(repo_name)
    на время этого вызова (см. workflows/engineering_task.py,
    workflows/squad_task.py) — это единственная операция во всей цепочке,
    которая трогает общий клон (checkout main -> merge -> push), а не
    изолированную per-task worktree, и поэтому единственная, где два
    параллельных вызова реально могут столкнуться друг с другом.

    Args:
        repo_name: 'bld-system' или 'bld-panel'.
        branch_name: ветка конкретной задачи, которую мержим в main
            (см. branch_prefix/slugify в workflows/engineering_task.py).
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
        # Worktree/ветку намеренно НЕ трогаем — конфликт нужно разобрать
        # руками, глядя именно на эту ветку.
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

    # Успех — подчищаем worktree и ветку, чтобы они не копились (это и
    # есть ответ на прошлое "не хочу, чтобы веток становилось много" —
    # см. коммент у AI_BRANCH_NAME выше). Любая ошибка здесь не критична
    # (main уже смержен и запушен — самое важное уже сделано) и не
    # должна маскировать успешный мерж как отказ.
    worktree_path = _get_active_worktree(repo_name)
    cleanup_note = ""
    if worktree_path is not None:
        wt_out = subprocess.run(
            ["git", "-C", str(path), "worktree", "remove", "--force", str(worktree_path)],
            capture_output=True, text=True,
        )
        if wt_out.returncode != 0:
            cleanup_note += f"\n(worktree не удалилась начисто, не критично: {wt_out.stderr.strip()})"
    subprocess.run(["git", "-C", str(path), "branch", "-D", branch_name], capture_output=True, text=True)
    subprocess.run(["git", "-C", str(path), "push", "origin", "--delete", branch_name], capture_output=True, text=True)
    _set_active_worktree(repo_name, None)

    return f"✅ {branch_name} смержен в main и запушен в origin. Ветка и рабочая копия подчищены.{cleanup_note}\n{merge_out.stdout.strip()}"
