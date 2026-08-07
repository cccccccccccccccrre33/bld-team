"""
Product Backlog — общая память компании для идей, которые НЕ обязаны
реализовываться прямо в момент, когда возникли.

Зачем это появилось: до этого файла в системе уже был
workflows/research_backlog.py — но он ЖЁСТКО ограничен FOUNDATIONAL_AREAS
(математика/физика/алгоритмы/архитектура). Всё остальное — обычные
продуктовые идеи, мелкие улучшения, наблюдения не по фундаментальным
темам — при archived/rejected/skip просто исчезало:
- workflows/individual_initiative.py::scout_and_propose — если
  can_take_more() уже False, человек вообще не сканирует, идея не
  успевает даже родиться.
- workflows/company_pulse.py::save_threads — ветка, которая не
  "ГОТОВО: ДА" и не попадает под FOUNDATIONAL_AREAS, при archive по
  MAX_ACTIVE_THREADS пропадала молча.
- workflows/domain_scan.py (новый) — весь смысл этого воркфлоу в том,
  что 612 человек смотрят на СВОЮ область каждый день; без общего
  места для результата это создало бы ровно ту же проблему на новом
  месте, только в больших масштабах.

Ключевое отличие от research_backlog.py: тот привязан к ТЕМЕ и не
предполагает "чьей" она была — сюда попадает то же самое, ПЛЮС
здесь есть pull-механизм: get_pull_candidate(personal_keywords)
позволяет чужому будущему сканированию (например,
individual_initiative::scout_and_propose следующего тика) сначала
проверить, нет ли уже замеченной, но не подхваченной идеи именно по
его специализации — прежде чем выдумывать с нуля. Это и есть ответ на
"как разгребать миллион идей": не хранилище-кладбище, а очередь,
которую предпочтительно вычерпывают, а не только пополняют.

Фильтрация ("важна идея или нет") по-прежнему делает не Валик, а
существующие агентные механизмы: workflows/cto_approval.py (CTO/
профильный эксперт) и workflows/company_pulse.py::assess_readiness —
этот backlog просто не даёт кандидатам исчезать ДО того, как они
дойдут до этой проверки.

Хранится в .state/product_backlog.json — тот же паттерн коммит/пуш в
git между запусками, что и у task_board/research_backlog/company_pulse.
"""

import json
import random
import subprocess
from datetime import datetime
from pathlib import Path

STATE_DIR = Path(".state")
BACKLOG_PATH = STATE_DIR / "product_backlog.json"

# Не растим бесконечно. Открытые записи НЕ обрезаются никогда (это и
# есть весь смысл бэклога) — обрезаются только закрытые, и только сверх
# лимита, старые первыми. Если открытых записей самих по себе больше
# этого числа — это не повод их терять, это сигнал (см.
# backlog_pressure() ниже), что скорость появления идей обгоняет
# скорость их разбора, и стоит смотреть на цифры, а не расширять лимит
# молча.
MAX_CLOSED_KEPT = 150


def _load() -> list[dict]:
    if not BACKLOG_PATH.exists():
        return []
    try:
        return json.loads(BACKLOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(entries: list[dict]) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    open_entries = [e for e in entries if e.get("status") != "closed"]
    closed_entries = sorted(
        (e for e in entries if e.get("status") == "closed"),
        key=lambda e: e.get("last_touched", ""),
        reverse=True,
    )[:MAX_CLOSED_KEPT]
    entries = open_entries + closed_entries
    BACKLOG_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", str(BACKLOG_PATH)], check=True)
        result = subprocess.run(
            ["git", "commit", "-m", "chore: product backlog — обновление"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[product_backlog] Не удалось сохранить в git: {e}")


def add_entry(
    title: str,
    summary: str,
    origin: str,
    scope: str = "неизвестно",
    participants: list[str] | None = None,
) -> str:
    """Кладёт новую идею в бэклог.

    origin — откуда пришла ('domain_scan' | 'company_pulse' |
    'individual_initiative' | 'lab_session' | 'chevruta' | ...).
    scope — 'мелкое' (можно брать прямо сейчас, не требует раздумий)
    или 'крупное' (стоит обдумать/обсудить перед тем, как кто-то
    возьмётся) — используется только для сортировки в format_summary,
    не блокирует ничего технически.
    """
    entries = _load()
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    entry_id = f"pb_{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(10, 99)}"
    entry = {
        "id": entry_id,
        "title": title.strip()[:200],
        "summary": summary.strip()[:600],
        "origin": origin,
        "scope": scope,
        "participants": participants or [],
        "status": "open",
        "created": now,
        "last_touched": now,
        "pulled_count": 0,
        "history": [],
    }
    entries.insert(0, entry)
    _save(entries)
    return entry_id


def get_pull_candidate(personal_keywords: list[str]) -> dict | None:
    """Ищет ОДНУ открытую запись, текст которой (title+summary)
    пересекается с personal_keywords человека, который сейчас сканирует
    СВОЮ область — тот же принцип 'kw in text', что и в
    individual_initiative.py::get_relevant_pulse_threads и
    hr_rotation_review.py::best_alternative_squad, тут не нужна новая
    схема сопоставления.

    Среди совпадений выбирает ту, что дольше всего не трогали
    (last_touched) — чтобы бэклог реально вычерпывался, а не одна и та
    же свежая запись подхватывалась раз за разом, пока старые тонут.
    None, если пересечений нет — вызывающий код просто продолжает как
    раньше, без подсказки."""
    if not personal_keywords:
        return None
    kws = [k.lower() for k in personal_keywords]
    open_entries = [e for e in _load() if e.get("status") == "open"]
    matches = [
        e for e in open_entries
        if any(kw in f"{e['title']} {e['summary']}".lower() for kw in kws)
    ]
    if not matches:
        return None
    matches.sort(key=lambda e: e.get("last_touched", ""))
    return matches[0]


def mark_pulled(entry_id: str) -> None:
    """Отмечает, что запись была ПОКАЗАНА кому-то как подсказка (не
    обязательно взята в работу) — двигает last_touched вперёд, чтобы
    следующий pull не предлагал ровно то же самое подряд, и считает
    pulled_count (если запись подряд много раз подсвечивается и НИКТО
    её не закрывает — это сигнал, что она никому не по зубам или
    неактуальна, видно через format_summary)."""
    entries = _load()
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    for e in entries:
        if e["id"] == entry_id:
            e["last_touched"] = now
            e["pulled_count"] = e.get("pulled_count", 0) + 1
            break
    _save(entries)


def mark_progress(entry_id: str, note: str, close: bool = False) -> None:
    """close=True — довели до задачи на task board (или признали
    неактуальной), пишем короткую заметку почему."""
    entries = _load()
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    for e in entries:
        if e["id"] == entry_id:
            e["last_touched"] = now
            e["history"] = (e.get("history", []) + [f"[{now}] {note.strip()[:300]}"])[-8:]
            e["status"] = "closed" if close else "open"
            break
    _save(entries)


def backlog_pressure() -> dict:
    """Сырые цифры для мониторинга: растёт ли бэклог быстрее, чем его
    разбирают. Не решает ничего сама — просто честный снимок, чтобы
    Валик (или executive_meeting.py в будущем) видел это по факту, а
    не по ощущению."""
    entries = _load()
    open_entries = [e for e in entries if e.get("status") == "open"]
    stale = [e for e in open_entries if e.get("pulled_count", 0) >= 3]
    by_origin: dict[str, int] = {}
    for e in open_entries:
        by_origin[e["origin"]] = by_origin.get(e["origin"], 0) + 1
    return {
        "open_total": len(open_entries),
        "open_never_pulled": sum(1 for e in open_entries if e.get("pulled_count", 0) == 0),
        "stale_ignored_3plus_pulls": len(stale),
        "by_origin": by_origin,
    }


def format_summary(limit: int = 10) -> str:
    entries = [e for e in _load() if e.get("status") == "open"][:limit]
    if not entries:
        return "(product backlog пока пуст)"
    lines = [f"📋 PRODUCT BACKLOG ({len(entries)} открытых записей):"]
    for e in entries:
        lines.append(f"  [{e['scope']}] {e['title']} (источник: {e['origin']}, с {e['created']})")
    return "\n".join(lines)
