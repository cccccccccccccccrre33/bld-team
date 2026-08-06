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
- rejected   : CTO отклонил с комментарием (осмысленное решение)
- timed_out  : процесс, выполнявший задачу, оборвался (обычно — job
               GitHub Actions убит по timeout-minutes), так и не
               обновив статус — НЕ то же самое, что rejected: тут
               никто ничего не отклонял, просто исполнение прервалось
               снаружи. См. reconcile_stale_tasks() ниже — статус
               выставляется автоматически, не CTO.

Каждая запись хранит "created" (когда заведена) и "updated" (когда в
последний раз менялся статус) — "updated" и есть то, по чему считается
"зависла ли задача", а не "created" (иначе задача, которая честно
неделю жила в "proposed" перед одобрением, засчиталась бы зависшей
сразу после перехода в in_progress).
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

STATE_DIR = Path(".state")
BOARD_PATH = STATE_DIR / "task_board.json"

# Максимум активных задач на всю компанию одновременно (in_progress).
# РАНЬШЕ было жёстко зашито в 4 — при ~186 людях с реальным write-доступом
# это означало, что почти вся компания физически не могла работать
# одновременно, сколько бы народу ни "хотело" взять задачу: не троттлинг
# по бюджету, а троттлинг по коду. По прямому запросу Валика ("людей
# много, добавляем сколько надо, не тупых") — лимит теперь читается из
# переменной окружения MAX_CONCURRENT_TASKS (задаётся в GitHub Actions
# vars, без правки кода), с дефолтом 12. Дефолт поднят, а не убран
# совсем — параллельный git push/merge в один и тот же main из
# слишком многих веток одновременно всё ещё реальный риск конфликтов,
# так что порог стоит поднимать постепенно, глядя на факт (сколько
# merge-конфликтов реально происходит), а не одним прыжком до "как
# людей".
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_TASKS", "12"))

# Сколько часов задача может честно висеть в in_progress/proposed,
# прежде чем считать её зависшей. Реальные timeout-minutes джобов в
# .github/workflows/*.yml — 10-45 минут (board_meeting: 20,
# squad_initiative: 25, individual_initiative: 20, chevruta: 15,
# lab_session: 15) — то есть если GitHub Actions убивает процесс по
# timeout, задача виснет уже в первый час. 2 часа — с большим запасом
# выше любого реального timeout-minutes, но всё ещё далеко от "дней",
# чтобы зомби не занимали слот MAX_CONCURRENT надолго.
STALE_HOURS = 2


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
             reason: str = "", how: str = "", goal_id: str | None = None) -> str:
    """Добавляет задачу на доску. Возвращает её task_id.

    goal_id — опционально: если задача заведена как часть цели,
    поставленной через /goal (workflows/goal_intake.py), сюда пишется
    общий идентификатор цели — так все подзадачи одной цели можно
    собрать вместе (см. get_tasks_by_goal()/list_open_goal_ids() ниже),
    даже если они разъехались по разным департаментам/эстафете/проекту.
    Для задач вне /goal остаётся None — поведение существующих вызовов
    не меняется."""
    board = _load()
    task_id = f"{squad}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    board["tasks"].append({
        "id": task_id,
        "title": title,
        "squad": squad,
        "status": status,
        "reason": reason,
        "how": how,
        "created": now,
        "updated": now,
        "cto_comment": "",
        # "participants" — ИМЕНА (как в agents/squads.py::member_names /
        # record_participation), кто фактически работал над задачей.
        # Заполняется ПОЗЖЕ, отдельным вызовом record_task_participants()
        # — на момент add_task() исполнители ещё обычно не известны
        # (задача может неделю простоять в proposed/approved). Пустой
        # список — не ошибка, просто "пока не известно" или "старая
        # запись до появления этого поля" (см. get_specialist_stats()
        # ниже — она честно игнорирует записи без участников).
        "participants": [],
        "goal_id": goal_id,
    })
    _save(board)
    return task_id


def record_task_participants(task_id: str, participants: list[str]) -> None:
    """Прикрепляет к задаче ФАКТИЧЕСКИХ исполнителей — вызывается из
    run_squad_task/run_squad_relay (workflows/squad_task.py) в момент,
    когда лид и пул уже определены, отдельно от update_task_status(),
    чтобы не завязывать это на конкретный статус (участники известны
    уже на старте выполнения, не только в момент done/rejected).

    Только ДОБАВЛЯЕТ новые имена (не затирает уже записанные). Нужна
    для get_specialist_stats() ниже — без неё вся статистика по задаче
    участвует, но обезличенно, и ротация (workflows/hr_rotation_review.py)
    не может опираться на факт, только на 'кто-то в этом отряде
    что-то делал'.
    """
    board = _load()
    for task in board["tasks"]:
        if task["id"] == task_id:
            existing = set(task.get("participants") or [])
            existing.update(participants)
            task["participants"] = sorted(existing)
            break
    _save(board)


def get_specialist_stats() -> dict[str, dict[str, int]]:
    """Агрегирует ПО ВСЕМ задачам доски: для каждого участника (имя как
    в record_task_participants/record_participation) — сколько задач с
    его участием закончились done / rejected / timed_out.

    Считает только задачи с непустым "participants" — записи без этого
    поля (старые, до появления record_task_participants, или задачи,
    где участников никто не прикрепил) просто не попадают в статистику.
    Это честная деградация на неполных данных, а не ошибка: раньше
    единственным сигналом "кто как работает" был .state/participation.json
    из workflows/_common.py::record_participation(), но там только
    ФАКТ участия ("когда в последний раз") — ни слова про то, довёл ли
    человек задачу до done или её отклонили/она зависла. Этот метод —
    первый источник данных, откуда вообще можно судить об исходе, а не
    только о частоте.

    timed_out НЕ считается ни успехом, ни провалом по существу (см.
    докстринг STALE_HOURS/reconcile_stale_tasks выше — обрыв процесса,
    не отказ) — но всё равно возвращается отдельным счётчиком,
    вызывающий код (hr_rotation_review.py) сам решает, как его учитывать.
    """
    board = _load()
    stats: dict[str, dict[str, int]] = {}
    for t in board["tasks"]:
        status = t.get("status")
        if status not in ("done", "rejected", "timed_out"):
            continue
        for name in (t.get("participants") or []):
            entry = stats.setdefault(name, {"done": 0, "rejected": 0, "timed_out": 0})
            entry[status] += 1
    return stats


def get_tasks_by_goal(goal_id: str) -> list[dict]:
    """Все задачи (любого статуса) с данным goal_id — подзадачи одной
    цели, поставленной через /goal (workflows/goal_intake.py), могли
    разъехаться по разным департаментам/эстафете/проекту, это
    единственное место, где их видно вместе."""
    board = _load()
    return [t for t in board["tasks"] if t.get("goal_id") == goal_id]


def list_open_goal_ids() -> list[str]:
    """Все goal_id, у которых есть хотя бы одна НЕзавершённая
    (proposed/approved/self_approved/in_progress) подзадача — то есть
    цель ещё в процессе. Используется workflows/goal_status.py для
    суточного обзора всех целей сразу, без того, чтобы Валику самому
    держать в голове, какие goal_id он вообще заводил."""
    board = _load()
    open_statuses = {"proposed", "approved", "self_approved", "in_progress"}
    open_ids = {
        t["goal_id"] for t in board["tasks"]
        if t.get("goal_id") and t.get("status") in open_statuses
    }
    return sorted(open_ids)


def update_task_status(task_id: str, status: str, cto_comment: str = "") -> None:
    board = _load()
    for task in board["tasks"]:
        if task["id"] == task_id:
            task["status"] = status
            task["updated"] = datetime.now().strftime("%d.%m.%Y %H:%M")
            if cto_comment:
                task["cto_comment"] = cto_comment
            break
    _save(board)


def _parse_ts(task: dict) -> datetime | None:
    """'updated' — авторитетный момент последнего изменения статуса.
    Для старых записей (созданных до появления этого поля) откатываемся
    на 'created' — лучше приблизительно, чем не проверять вообще."""
    raw = task.get("updated") or task.get("created")
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%d.%m.%Y %H:%M")
    except Exception:
        return None


def find_stale_tasks(stale_hours: int = STALE_HOURS) -> list[dict]:
    """Только СМОТРИТ — какие задачи в in_progress/proposed висят дольше
    stale_hours часов, ничего не меняет. Отдельно от reconcile_stale_tasks(),
    чтобы можно было посмотреть перед тем как реально исправлять (см.
    tools/unstick_task_board.py — сухой прогон использует эту функцию)."""
    board = _load()
    now = datetime.now()
    stale = []
    for t in board["tasks"]:
        if t["status"] not in ("in_progress", "proposed"):
            continue
        when = _parse_ts(t)
        if when is None:
            continue
        age_hours = (now - when).total_seconds() / 3600
        if age_hours >= stale_hours:
            entry = dict(t)
            entry["_age_hours"] = age_hours
            stale.append(entry)
    return stale


def reconcile_stale_tasks(stale_hours: int = STALE_HOURS, notify: bool = True) -> list[dict]:
    """Реально помечает зависшие задачи статусом 'timed_out' (см.
    докстринг модуля — это НЕ 'rejected': тут никто ничего не отклонял
    по существу, процесс просто оборвался снаружи, обычно потому что
    GitHub Actions job убивает выполнение по timeout-minutes сигналом,
    который try/except внутри Python в принципе не может поймать).

    Коммитит изменение, только если реально что-то нашлось — не гоняет
    git попусту. По умолчанию шлёт короткое уведомление в Telegram
    (одним сообщением на все найденные сразу), чтобы Валик узнавал об
    этом сам, а не только читая task_board.json руками.

    Раньше единственным способом почистить это было вручную запустить
    tools/unstick_task_board.py --apply — то есть кто-то должен был сам
    вспомнить и нажать кнопку. Теперь это встроено в get_active_tasks()
    (см. ниже) и происходит само по себе на каждом цикле любого
    воркфлоу компании, плюс отдельный cron в
    .github/workflows/unstick_task_board.yml как подстраховка."""
    stale = find_stale_tasks(stale_hours)
    if not stale:
        return []

    board = _load()
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    stale_ids = {t["id"] for t in stale}
    for t in board["tasks"]:
        if t["id"] in stale_ids:
            was_status = t["status"]
            t["status"] = "timed_out"
            t["updated"] = now_str
            t["cto_comment"] = (
                (t.get("cto_comment") or "") +
                f" [Авто-разморозка {now_str}: висела в '{was_status}' дольше {stale_hours}ч без "
                "изменений — похоже, выполнявший процесс оборвался (обычно это GitHub Actions "
                "убивает job по timeout-minutes), а не что кто-то отклонил задачу по существу. "
                "Слот освобождён. Если задача про реальный код (in_progress) — ветка могла "
                "остаться в частично изменённом состоянии, стоит проверить репозиторий вручную, "
                "прежде чем переоткрывать тему заново.]"
            ).strip()
    board["last_updated"] = now_str
    _save(board)

    if notify:
        _notify_stale(stale, stale_hours)
    return stale


def _notify_stale(stale: list[dict], stale_hours: int) -> None:
    lines = [f"⏱️ АВТО-РАЗМОРОЗКА ЗАВИСШИХ ЗАДАЧ ({len(stale)} шт., висели дольше {stale_hours}ч):"]
    for t in stale:
        lines.append(f"  [{t.get('squad', '?')}] ({t['status']} → timed_out, {t['_age_hours']:.1f}ч): {t.get('title', '')[:100]}")
    lines.append(
        "\nЭто НЕ отказ CTO — просто выполнявший процесс где-то оборвался "
        "(чаще всего таймаут GitHub Actions job), слот освобождён автоматически. "
        "Если среди них есть in_progress — стоит глянуть ветку в репозитории, "
        "не осталась ли она в недописанном состоянии, прежде чем переоткрывать тему."
    )
    # Импорт нарочно ленивый и обёрнут целиком (не только сам вызов):
    # workflows/task_board.py и особенно tools/unstick_task_board.py
    # (у него в .github/workflows/unstick_task_board.yml нет шага pip
    # install — раньше скрипт был на чистом stdlib, и это осознанно, он
    # последняя линия защиты и должен запускаться даже если что-то
    # другое в окружении сломано) не обязаны иметь "requests"
    # установленным, чтобы просто посчитать активные задачи — а вот
    # уведомление в Telegram, если библиотека есть, всё равно уйдёт.
    try:
        from tools.telegram_report import send_telegram_report
        send_telegram_report("\n".join(lines))
    except Exception as e:
        print(f"[task_board] Не удалось отправить уведомление об авто-разморозке (не критично): {e}")


_stale_check_done_this_run = False


def get_active_tasks() -> list[dict]:
    """Задачи в статусе in_progress прямо сейчас. Перед подсчётом ОДИН
    РАЗ за запуск процесса подчищает зависшие задачи (reconcile_stale_tasks) —
    без этого одна убитая GitHub Actions job навсегда съедала бы слот
    MAX_CONCURRENT, и с каждым таким зависанием реальная параллельность
    системы тихо сокращалась бы, а не росла (см. workflows/board_meeting.py,
    workflows/squad_initiative.py — оба считают ёмкость через эту функцию).

    Флаг-guard на модульном уровне не даёт дёргать git на КАЖДЫЙ вызов
    в рамках одного запуска (get_active_tasks() может вызываться
    несколько раз за один прогон воркфлоу) — реконсиляция реально
    нужна не чаще раза в запуск, следующий прогон (через 10-30 минут,
    см. расписания в .github/workflows/) подхватит всё новое сам."""
    global _stale_check_done_this_run
    if not _stale_check_done_this_run:
        _stale_check_done_this_run = True
        try:
            reconcile_stale_tasks()
        except Exception as e:
            print(f"[task_board] Авто-разморозка зависших задач не удалась в этот раз (не критично): {e}")

    board = _load()
    return [t for t in board["tasks"] if t["status"] == "in_progress"]


DUPLICATE_REJECTED_LOOKBACK_DAYS = 7
# Сколько дней после явного rejected CTO та же (по пересечению слов)
# тема считается дублем. Раньше is_duplicate() смотрел только на
# proposed/approved/self_approved/in_progress — из-за этого один и тот
# же localhost-fallback три раза подряд заводили разные squad'ы, и CTO
# трижды перепроверял и объяснял, что это уже не проблема (см.
# task_board.json — три "bravo" задачи про http://localhost fallback,
# все rejected с почти одинаковым комментарием). timed_out сюда
# СОЗНАТЕЛЬНО не входит: это не отказ CTO по существу, а обрыв
# исполнения — повторное предложение для timed_out штатный путь retry,
# см. STATUS_LABELS в get_board_summary() и docstring статусов вверху
# файла. Окно в 7 дней — компромисс: не даёт тут же переспросить то,
# что только что отклонили, но не блокирует навсегда тему, если
# обстоятельства реально изменились.


def is_duplicate(title: str) -> bool:
    """True если похожая задача уже есть в активных/proposed/approved,
    либо была явно отклонена CTO (rejected) в пределах последних
    DUPLICATE_REJECTED_LOOKBACK_DAYS дней."""
    board = _load()
    active_statuses = {"proposed", "approved", "self_approved", "in_progress"}
    title_words = {w for w in title.lower().split() if len(w) > 4}

    def _overlaps(other_title: str) -> bool:
        other_words = {w for w in other_title.lower().split() if len(w) > 4}
        return len(title_words & other_words) >= 2

    now = datetime.now()
    for t in board["tasks"]:
        if t["status"] in active_statuses:
            if _overlaps(t["title"]):
                return True
            continue
        if t["status"] == "rejected" and _overlaps(t["title"]):
            try:
                updated = datetime.strptime(t.get("updated", ""), "%d.%m.%Y %H:%M")
            except ValueError:
                # Не можем разобрать дату — перестраховываемся и всё
                # равно считаем дублем, а не молча пропускаем проверку.
                return True
            if (now - updated).days < DUPLICATE_REJECTED_LOOKBACK_DAYS:
                return True
    return False


def can_take_more() -> bool:
    """True если лимит параллельных задач не исчерпан."""
    return len(get_active_tasks()) < MAX_CONCURRENT


def available_capacity() -> int:
    """Сколько ещё задач можно взять в работу ПРЯМО СЕЙЧАС, не превышая
    MAX_CONCURRENT — в отличие от can_take_more() (просто да/нет),
    отдаёт конкретное число. Нужно там, где нужно решить не "можно ли
    взять ещё одну", а "скольким отрядам/людям одновременно можно дать
    задачу в этом цикле" (см. workflows/board_meeting.py — раньше
    рассинхрон между этим модулем и board_meeting.py приводил к тому,
    что задачи от совета директоров вообще не учитывались в лимите)."""
    return max(0, MAX_CONCURRENT - len(get_active_tasks()))


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
        "timed_out": "⏱️ Зависла и автоматически разморожена (не отказ CTO — можно переоткрыть)",
        "needs_founder_decision": "🧑‍💻 Требует решения/действия Валика лично",
    }
    for status, label in STATUS_LABELS.items():
        tasks = by_status.get(status, [])
        if tasks:
            lines.append(f"\n{label}:")
            for t in tasks:
                lines.append(f"  [{t['squad']}] {t['title']}")

    return "\n".join(lines)
