"""
CLI для разгребания зависших задач в .state/task_board.json — ручной
доступ к той же логике, что теперь встроена в workflows/task_board.py
(reconcile_stale_tasks) и срабатывает АВТОМАТИЧЕСКИ на каждом прогоне
любого воркфлоу компании (через get_active_tasks()), плюс отдельным
cron'ом в .github/workflows/unstick_task_board.yml как подстраховка.

Раньше это был "разовый скрипт" (см. историю в git) — реализация
дублировала свою собственную копию проверки таймстампов прямо здесь и
запускалась только руками через workflow_dispatch. Это и было причиной
того, что зависшие задачи копились неделями: единственный способ их
разморозить требовал, чтобы кто-то вспомнил зайти в GitHub Actions и
нажать кнопку. Теперь эта функция ЖИВЁТ в workflows/task_board.py
(единый источник правды, как и остальная логика доски задач), а этот
файл — просто тонкая обёртка для ручного/CI-запуска.

Использование (из корня репозитория bld-team, где лежит .state/):
    python tools/unstick_task_board.py            # только посмотреть, ничего не менять
    python tools/unstick_task_board.py --apply     # реально исправить и закоммитить
"""

import argparse
import sys
from pathlib import Path

# Запуск как "python tools/unstick_task_board.py" кладёт на sys.path
# только саму папку tools/, а не корень репозитория — без этой строки
# "from workflows.task_board import ..." ниже падает с
# ModuleNotFoundError (проверено вручную перед коммитом). main_*.py в
# корне репозитория с этим не сталкиваются, потому что и так уже лежат
# в корне — а этот скрипт находится на уровень глубже.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workflows.task_board import STALE_HOURS, find_stale_tasks, reconcile_stale_tasks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="реально сохранить изменения, закоммитить и уведомить в Telegram")
    parser.add_argument("--hours", type=float, default=STALE_HOURS, help=f"порог в часах (по умолчанию {STALE_HOURS})")
    args = parser.parse_args()

    if not args.apply:
        stale = find_stale_tasks(args.hours)
        if not stale:
            print(f"Зависших задач (старше {args.hours}ч) не найдено.")
            return
        print(f"Найдено зависших задач: {len(stale)} (порог: {args.hours}ч)\n")
        for t in stale:
            print(f"  [{t.get('squad', '?')}] ({t['status']}, {t['_age_hours']:.1f}ч): {t.get('title', '')[:90]}")
        print("\n(сухой прогон — ничего не изменено; добавь --apply чтобы реально пометить как timed_out и закоммитить)")
        return

    fixed = reconcile_stale_tasks(args.hours, notify=True)
    if not fixed:
        print(f"Зависших задач (старше {args.hours}ч) не найдено — база уже чистая.")
        return
    print(f"Разморожено задач: {len(fixed)} (помечены как 'timed_out', закоммичено, отправлено уведомление в Telegram).")


if __name__ == "__main__":
    main()
