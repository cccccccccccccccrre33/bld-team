"""
Backlog фундаментальных исследований — постоянная память для идей,
которые НЕ являются "тикетом на реализацию прямо сейчас", а
принадлежат к фундаментальным направлениям (математика, физика,
алгоритмы, архитектура, инженерные основы) и раньше просто испарялись:

- Лаборатория (lab_session.py): если группа без доступа к коду
  обсуждала абстрактную проблему, или CTO не одобрил извлечённую
  задачу — отчёт уходил в Telegram и одной строкой в вики, и всё.
  Ни малейшего способа "вернуться к этому через неделю".
- Хеврута (chevruta.py): если кумир (CTO/CEO) НЕ сказал "В
  РЕАЛИЗАЦИЮ" — интересная мысль пропадала точно так же.
- Company Pulse (company_pulse.py): ветки чата, которые не "дозрели"
  до ГОТОВО:ДА, архивировались молча, как только выходили за пределы
  MAX_ACTIVE_THREADS (6 самых свежих) — включая содержательные
  фундаментальные обсуждения, которые просто не успели дозреть за
  один тик.

Идея модуля: не каждая хорошая мысль обязана реализоваться с первого
захода. У фундаментальных направлений (в отличие от рутинных
багфиксов) плодотворный цикл обычно и должен занимать недели — надо
куда-то её положить и суметь вернуться, а не заставлять решаться с
первого раза под страхом полной потери.

Не путать с личным дневником (NOTEBOOKS_DIR в workflows/_common.py —
непрерывность ОДНОГО человека): этот backlog общий на всю компанию и
привязан к ТЕМЕ, а не к человеку — любой, кто наткнётся на неё снова
(не обязательно тот же состав людей), может её поднять.

Хранится в .state/research_backlog.json, коммитится в репозиторий
bld-team — тот же паттерн, что и вики/доска задач/дневники.
"""

import json
import random
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

STATE_DIR = Path(".state")
BACKLOG_PATH = STATE_DIR / "research_backlog.json"

MAX_BACKLOG_SIZE = 60  # не растим бесконечно; закрытые записи вытесняются первыми

# Ключевые слова для классификации области — используются ТОЛЬКО чтобы
# пометить, к какому фундаментальному направлению ближе идея (и чтобы
# company_pulse.py мог решить, достойна ли затихающая ветка архивации
# сюда). Решение "класть ли вообще в backlog" принимает вызывающий код
# (lab_session/chevruta) по контексту происхождения — здесь только
# классификация уже принятых записей.
AREA_KEYWORDS = {
    "математика": ["теорем", "доказательств", "вероятностн", "статистич", "матриц", "оптимизац", "алгебр", "распределен"],
    "физика": ["физич", "термодинам", "энтроп", "сигнал", "шум", "модель распростран", "затуха"],
    "алгоритмы": ["алгоритм", "сложност", "структур данных", "граф", "поиск", "сортировк", "hashing", "индекс"],
    "архитектура": ["архитектур", "модульност", "связанност", "слой", "паттерн проектирован", "интерфейс между"],
    "инженерия": ["инженерн", "надёжност", "тестирован", "деплой", "производительност", "масштабиру"],
}

# Направления, которые company_pulse.py считает достаточно "фундаментальными",
# чтобы спасать затихающую ветку от полного исчезновения (см. company_pulse.py).
FOUNDATIONAL_AREAS = {"математика", "физика", "алгоритмы", "архитектура"}


def classify_area(*texts: str) -> str:
    joined = " ".join(t.lower() for t in texts if t)
    for area, keywords in AREA_KEYWORDS.items():
        if any(kw in joined for kw in keywords):
            return area
    return "другое"


def _load() -> list[dict]:
    if not BACKLOG_PATH.exists():
        return []
    try:
        return json.loads(BACKLOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(entries: list[dict]) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    # Открытые записи сохраняем всегда; закрытые обрезаем по лимиту,
    # чтобы файл не рос бесконечно — но не теряем историю мгновенно.
    # (То, что реально стоит помнить вечно, и так уходит в
    # company_wiki.md через curate_knowledge — этот файл лишь рабочая
    # память "к чему стоит вернуться", а не архив.)
    open_entries = [e for e in entries if e.get("status") != "closed"]
    closed_entries = [e for e in entries if e.get("status") == "closed"]
    entries = (open_entries + closed_entries)[:MAX_BACKLOG_SIZE]
    BACKLOG_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", str(BACKLOG_PATH)], check=True)
        result = subprocess.run(
            ["git", "commit", "-m", "chore: research backlog — обновление"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[research_backlog] Не удалось сохранить в git: {e}")


def add_entry(topic: str, summary: str, origin: str, participants: list[str] | None = None,
              area: str | None = None) -> str:
    """Кладёт новую идею в backlog. area определяется автоматически по
    ключевым словам темы+саммари, если не передана явно. origin —
    откуда пришла идея ('lab_session' | 'chevruta' | 'company_pulse')."""
    entries = _load()
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    entry_id = f"rb_{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(10, 99)}"
    entry = {
        "id": entry_id,
        "area": area or classify_area(topic, summary),
        "topic": topic.strip(),
        "summary": summary.strip()[:600],
        "origin": origin,
        "participants": participants or [],
        "status": "open",
        "created": now,
        "last_touched": now,
        "revisit_count": 0,
        "history": [],
    }
    entries.insert(0, entry)
    _save(entries)
    return entry_id


def get_revisit_candidate(min_age_days: int = 5, origin: str | None = None) -> dict | None:
    """Возвращает ОДНУ самую давно нетронутую ОТКРЫТУЮ запись backlog'а
    (не трогали минимум min_age_days) — не важно, чья это идея
    изначально. Если origin передан — предпочитает записи именно
    этого происхождения (лаборатория в первую очередь подхватывает
    темы, рождённые в лаборатории же, но может взять и из хевруты/
    pulse, если своих подходящих сейчас нет). None, если подходящих
    нет вообще (backlog пуст или все записи слишком свежие)."""
    entries = [e for e in _load() if e.get("status") == "open"]
    if not entries:
        return None

    cutoff = datetime.now() - timedelta(days=min_age_days)

    def touched_at(e: dict) -> datetime:
        try:
            return datetime.strptime(e["last_touched"], "%d.%m.%Y %H:%M")
        except Exception:
            return datetime.now()

    stale = [e for e in entries if touched_at(e) <= cutoff]
    if not stale:
        return None
    stale.sort(key=touched_at)  # самая давно нетронутая — первая

    if origin:
        same_origin = [e for e in stale if e.get("origin") == origin]
        if same_origin:
            return same_origin[0]
    return stale[0]


def mark_revisited(entry_id: str, note: str, close: bool = False) -> None:
    """Отмечает, что backlog-запись снова подняли — двигает
    last_touched вперёд (чтобы не предлагать её на КАЖДОЙ следующей
    сессии подряд) и дописывает короткую заметку в историю.
    close=True — тема реально закрыта (доведена до кода или признана
    исчерпанной участниками)."""
    entries = _load()
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    for e in entries:
        if e["id"] == entry_id:
            e["last_touched"] = now
            e["revisit_count"] = e.get("revisit_count", 0) + 1
            e["history"] = (e.get("history", []) + [f"[{now}] {note.strip()[:300]}"])[-8:]
            e["status"] = "closed" if close else "open"
            break
    _save(entries)


def format_entry_for_prompt(entry: dict) -> str:
    return (
        f"Тема из backlog'а фундаментальных исследований (область: {entry['area']}, "
        f"впервые всплыла {entry['created']}, поднималась уже {entry['revisit_count']} раз(а)):\n"
        f"{entry['topic']}\n"
        f"Суть на момент последнего обсуждения: {entry['summary']}"
    )


def format_backlog_summary(limit: int = 8) -> str:
    """Короткий текстовый срез открытых тем — для контекста человеку/
    отчёту, не для автоматического выбора (выбор делает
    get_revisit_candidate)."""
    entries = [e for e in _load() if e.get("status") == "open"][:limit]
    if not entries:
        return "(research backlog пока пуст)"
    lines = [f"🧠 RESEARCH BACKLOG ({len(entries)} открытых тем):"]
    for e in entries:
        lines.append(f"  [{e['area']}] {e['topic']} (с {e['created']}, поднималась {e['revisit_count']}×)")
    return "\n".join(lines)
