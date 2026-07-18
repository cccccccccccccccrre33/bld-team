"""
Разовый скрипт для разгребания зависших задач в .state/task_board.json.

Проблема: до фикса в engineering_task.py/company_pulse.py и т.д. исключение
внутри run_engineering_task() навсегда оставляло задачу в статусе
"in_progress" — что упёрлось в MAX_CONCURRENT=4 и молча заблокировало
individual_initiative/squad_initiative.

Запуск (из корня репозитория bld-team, где лежит .state/):
    python tools/unstick_task_board.py            # только посмотреть
    python tools/unstick_task_board.py --apply     # реально исправить и закоммитить

Логика: все задачи в статусе "in_progress" старше STALE_HOURS часов
считаются зависшими (после фикса реализация занимает минуты, не дни) и
переводятся в "rejected" с пометкой, что это ручная реконсиляция —
их нужно будет переоткрыть по новой, если тема ещё актуальна.
"""

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

BOARD_PATH = Path(".state/task_board.json")
STALE_HOURS = 2  # с новым кодом реализация не должна висеть дольше


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="реально сохранить изменения и закоммитить")
    args = parser.parse_args()

    board = json.loads(BOARD_PATH.read_text(encoding="utf-8"))
    now = datetime.now()

    changed = 0
    for t in board["tasks"]:
        if t["status"] != "in_progress":
            continue
        created = datetime.strptime(t["created"], "%d.%m.%Y %H:%M")
        age_hours = (now - created).total_seconds() / 3600
        if age_hours < STALE_HOURS:
            continue
        print(f"ЗАВИСЛА ({age_hours:.0f}ч): [{t['squad']}] {t['title'][:80]}")
        if args.apply:
            t["status"] = "rejected"
            t["cto_comment"] = (
                (t.get("cto_comment") or "")
                + f" [Реконсиляция {now.strftime('%d.%m.%Y %H:%M')}: задача зависла из-за необработанного "
                "исключения в старой версии engineering_task.py, автоматически закрыта. "
                "Если тема ещё актуальна — предложите заново, теперь она пройдёт через защищённый пайплайн.]"
            ).strip()
            changed += 1

    if not args.apply:
        print(f"\n(сухой прогон — {changed if changed else 'см. выше'} задач будет затронуто; добавь --apply чтобы применить)")
        return

    board["last_updated"] = now.strftime("%d.%m.%Y %H:%M")
    BOARD_PATH.write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nИсправлено задач: {changed}. Коммичу...")

    subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
    subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add", str(BOARD_PATH)], check=True)
    subprocess.run(["git", "commit", "-m", "chore: реконсиляция зависших in_progress задач task board"], check=True)
    subprocess.run(["git", "push"], check=True)
    print("Готово.")


if __name__ == "__main__":
    main()
