"""
Общая доска задач — единственный источник правды о том, что сейчас
в работе, что сделано, что одобрено CTO, что ждёт approval.

Хранится в .state/task_board.json в репозитории bld-team (коммитится
обратно как и вики, topics и rotation state). Все отряды читают её
перед тем как взять задачу — так никто не дублирует работу другого.

Статусы задачи:
- proposed  : отряд предложил, ждёт approval CTO
- approved  : CTO одобрил, отряд может выполнять
- self_approved: отряд взял сам (мелкая задача, не требует approval)
- in_progress: выполняется прямо сейчас
- done       : ветка запушена, Review Gate пройден
- rejected   : CTO отклонил с комментарием
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path

STATE_DIR = Path(".state")
BOARD_PATH = STATE_DIR / "task_board.json"

# Максимум активных задач на всю компанию одновременно (in_progress).
# Защита от "все взяли всё одновременно и начался хаос".
MAX_CONCURRENT = 4


def _load() -> dict:
    if not BOARD_PATH.exists():
        return {"tasks": [], "last_updated": ""}
    try:
        return json.loads(BOARD_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"tasks": [], "last_updated": ""}


def _save(board: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    board["last_updated"] = datetime.now().strftime("%d.%m.%Y %H:%M")
    BOARD_PATH.write_text(
        json.dumps(board, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(
            ["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"],
            check=True,
        )
        subprocess.run(["git", "add", str(BOARD_PATH)], check=True)
        result = subprocess.run(
            ["git", "commit", "-m", "chore: обновление task board"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[task_board] git push не удался: {e}")


def add_task(title: str, squad: str, status: str = "proposed",
             reason: str = "", how: str = "") -> str:
    """Добавляет задачу на доску. Возвращает её task_id."""
    board = _load()
    task_id = f"{squad}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    board["tasks"].append({
        "id": task_id,
        "title": title,
        "squad": squad,
        "status": status,
        "reason": reason,
        "how": how,
        "created": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "cto_comment": "",
    })
    _save(board)
    return task_id


def update_task_status(task_id: str, status: str, cto_comment: str = "") -> None:
    board = _load()
    for task in board["tasks"]:
        if task["id"] == task_id:
            task["status"] = status
            if cto_comment:
                task["cto_comment"] = cto_comment
            break
    _save(board)


def get_active_tasks() -> list[dict]:
    """Задачи в статусе in_progress прямо сейчас."""
    board = _load()
    return [t for t in board["tasks"] if t["status"] == "in_progress"]


def is_duplicate(title: str) -> bool:
    """True если похожая задача уже есть в активных/proposed/approved."""
    board = _load()
    active_statuses = {"proposed", "approved", "self_approved", "in_progress"}
    existing = [t["title"].lower() for t in board["tasks"]
                if t["status"] in active_statuses]
    title_lower = title.lower()
    # Простая проверка: пересечение значимых слов (>4 символов)
    title_words = {w for w in title_lower.split() if len(w) > 4}
    for existing_title in existing:
        existing_words = {w for w in existing_title.split() if len(w) > 4}
        overlap = title_words & existing_words
        if len(overlap) >= 2:
            return True
    return False


def can_take_more() -> bool:
    """True если лимит параллельных задач не исчерпан."""
    return len(get_active_tasks()) < MAX_CONCURRENT


def get_board_summary() -> str:
    """Короткий текстовый срез для показа отрядам перед поиском задачи."""
    board = _load()
    if not board["tasks"]:
        return "Доска пустая — задач ещё не было."

    lines = [f"📋 TASK BOARD (обновлено: {board.get('last_updated', '?')})"]
    by_status = {}
    for t in board["tasks"][-20:]:  # последние 20, не гоним весь архив
        s = t["status"]
        by_status.setdefault(s, []).append(t)

    STATUS_LABELS = {
        "proposed": "⏳ Ожидают approval CTO",
        "approved": "✅ Одобрено, берём в работу",
        "self_approved": "🔓 Взято самостоятельно (мелкое)",
        "in_progress": "🔄 В работе прямо сейчас",
        "done": "✔️  Выполнено",
        "rejected": "❌ Отклонено CTO",
    }
    for status, label in STATUS_LABELS.items():
        tasks = by_status.get(status, [])
        if tasks:
            lines.append(f"\n{label}:")
            for t in tasks:
                lines.append(f"  [{t['squad']}] {t['title']}")

    return "\n".join(lines)
