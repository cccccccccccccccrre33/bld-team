"""
Автосборщик стартового context/company_context.md.

Идея: человек скачивает форк, указывает TARGET_REPOS (см.
tools/repo_tools.py) — и НЕ обязан вручную писать контекстный файл
с нуля, прежде чем агенты станут полезны. При первом запуске (см.
ensure_company_context(), вызывается из workflows/_common.py сразу
после клонирования репозиториев) это модуль читает README, дерево
файлов и манифесты зависимостей каждого целевого репозитория и
собирает из этого черновик — тот же формат секций
(## Кто мы / ## Что такое <проект> / ## Как должна работать AI-команда),
который использует agents/_shared_context.py.

ВАЖНО: это ЧЕРНОВИК, не замена ручного контекста. Технические детали,
которые не видны из README/структуры файлов (архитектурные инварианты,
бизнес-приоритеты, известные проблемы) — read_me не может их знать.
README проекта прямо говорит: отредактируй company_context.md под себя,
как только увидишь, что дискуссии реальны, но обобщённы. Если файл уже
существует — ensure_company_context() его не трогает.
"""

from __future__ import annotations

from pathlib import Path

_CONTEXT_PATH = (
    Path(__file__).resolve().parent.parent / "context" / "company_context.md"
)

_README_CANDIDATES = ("README.md", "readme.md", "Readme.md", "README.rst", "README.txt")
_MANIFEST_FILES = (
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "composer.json",
)


def _find_readme(repo_path: Path) -> str:
    for candidate in _README_CANDIDATES:
        f = repo_path / candidate
        if f.exists():
            text = f.read_text(errors="ignore").strip()
            return text[:3000] + ("\n...[обрезано]" if len(text) > 3000 else "")
    return "(README не найден в корне репозитория)"


def _detect_stack(repo_path: Path) -> list[str]:
    found = []
    for manifest in _MANIFEST_FILES:
        if (repo_path / manifest).exists():
            found.append(manifest)
    return found


def _top_level_tree(repo_path: Path, max_entries: int = 25) -> str:
    ignore = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}
    entries = [p.name + ("/" if p.is_dir() else "") for p in sorted(repo_path.iterdir())
               if p.name not in ignore]
    shown = entries[:max_entries]
    tree = "\n".join(f"- {e}" for e in shown)
    if len(entries) > max_entries:
        tree += f"\n- ...ещё {len(entries) - max_entries} элементов"
    return tree or "(пусто)"


def build_context_draft(repos: dict, workdir: Path) -> str:
    """Собирает markdown-черновик company_context.md по всем репозиториям
    из repos ({name: url}), уже склонированным в workdir/name."""
    sections = [
        "# Контекст компании (черновик, собран автоматически)\n",
        (
            "Это единственный источник правды о том, чем занимается проект и "
            "как должна работать сама AI-команда — читает agents/_shared_context.py "
            "и получают все технические роли. Отредактируй этот файл руками, "
            "когда увидишь, чего автосборке не хватает (README редко объясняет "
            "архитектурные инварианты, бизнес-приоритеты или известные проблемы) "
            "— агенты подхватят изменения при следующем запуске.\n"
        ),
        "---\n",
        "## Кто мы\n",
        (
            "*(Заполни: кто ты, какая цель у проекта, чем в первую очередь "
            "должна руководствоваться команда при спорных решениях — "
            "например, скорость выхода фич важнее идеальной архитектуры, "
            "или наоборот.)*\n"
        ),
        "---\n",
    ]

    for name, url in repos.items():
        repo_path = workdir / name
        if not repo_path.exists():
            continue
        readme = _find_readme(repo_path)
        stack = _detect_stack(repo_path)
        tree = _top_level_tree(repo_path)
        sections.append(f"## Что такое {name}\n")
        sections.append(f"Репозиторий: `{url}`\n")
        if stack:
            sections.append(f"Обнаруженные файлы-манифесты (стек): {', '.join(stack)}\n")
        sections.append("**Структура верхнего уровня:**\n")
        sections.append(tree + "\n")
        sections.append("**Из README:**\n")
        sections.append(f"> {readme}\n")
        sections.append("---\n")

    sections.append("## Как должна работать сама AI-команда (операционная культура)\n")
    sections.append(_DEFAULT_CULTURE_SECTION)

    return "\n".join(sections)


# Генерическая версия операционной культуры — сам принцип (не соглашаться
# для вежливости, ссылаться на реальный код, вето у ревью, честность
# важнее приятных отчётов, обсуждение и реализация — разные режимы)
# универсален и не привязан к конкретному проекту, поэтому используется
# как разумный дефолт для автосборки.
_DEFAULT_CULTURE_SECTION = """
**Обсуждение, а не вежливый обмен репликами.** Никто не соглашается с
коллегой просто потому что тот сказал что-то разумное — если есть риск,
альтернатива или цена вопроса, об этом говорят прямо, а утверждения без
опоры на реальный код проверяются через инструменты чтения репозитория,
а не принимаются на веру.

**Обсуждение и реализация — разные режимы.** В режиме дискуссии агенты
разбирают код теоретически и словами объясняют, что не так и что
делать, но не пишут и не коммитят код — это отдельный, явно выданный
режим/задача.

**Честность важнее приятных отчётов.** Если задача не осмысленная или
решение не докручено — так и сообщается, без приукрашивания.

*(Дополни этот раздел под свой проект: какие роли имеют право вето,
кто финально мержит в main, как распределяется бюрократия между
специализациями — см. пример полной версии в
context/company_context.template.md.)*
"""


def ensure_company_context(repos: dict, workdir: Path) -> bool:
    """Если context/company_context.md ещё не существует — генерирует
    черновик из целевых репозиториев и сохраняет его туда. Возвращает
    True, если файл был создан этим вызовом (для лога), False если файл
    уже был или сборка не дала ничего полезного."""
    if _CONTEXT_PATH.exists():
        return False
    try:
        draft = build_context_draft(repos, workdir)
    except Exception as e:  # noqa: BLE001 — сборка контекста не должна ронять весь запуск
        print(f"[context_builder] Не удалось собрать черновик контекста: {e}")
        return False
    _CONTEXT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONTEXT_PATH.write_text(draft, encoding="utf-8")
    print(
        f"[context_builder] context/company_context.md не найден — собрал "
        f"черновик из {len(repos)} репозитори(ев). Рекомендуется открыть "
        "файл и дополнить его вручную (бизнес-приоритеты, известные "
        "проблемы, кто ты) — README не может рассказать об этом."
    )
    return True
