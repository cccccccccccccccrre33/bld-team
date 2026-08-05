"""
goal_status.py — статус целей, заведённых через /goal (workflows/goal_intake.py).

Каждая подзадача цели попадает на доску (workflows/task_board.py) с
общим полем goal_id (см. add_task() там же). Этот модуль группирует
задачи по goal_id и показывает, сколько done / в работе / отклонено —
это и есть замыкающий шаг спецификации /goal ("шаг 4: раз в день
проверяет, все ли подзадачи done, шлёт финальный отчёт") — без него
Валику пришлось бы самому помнить каждый goal_id и вручную сверяться с
доской, что снова было бы "не писать промпты, но следить руками".
"""

import asyncio

from tools.telegram_report import send_telegram_report
from workflows.task_board import get_tasks_by_goal, list_open_goal_ids

STATUS_MARKERS = {
    "done": "✔️", "rejected": "❌", "timed_out": "⏱️",
    "in_progress": "🔄", "proposed": "⏳", "approved": "✅",
    "self_approved": "🔓", "needs_founder_decision": "🧑‍💻",
}


def summarize_goal(goal_id: str) -> str:
    tasks = get_tasks_by_goal(goal_id)
    if not tasks:
        return f"🎯 Цель {goal_id}: подзадач на доске не найдено (goal_id неверный, или подзадачи ещё не зарегистрированы)."

    done = sum(1 for t in tasks if t["status"] == "done")
    closed = sum(1 for t in tasks if t["status"] in ("done", "rejected", "timed_out"))
    total = len(tasks)

    lines = [f"🎯 Цель {goal_id} — {done}/{total} подзадач выполнено:"]
    for t in tasks:
        marker = STATUS_MARKERS.get(t["status"], "•")
        lines.append(f"  {marker} [{t['squad']}] {t['title']} ({t['status']})")

    if closed == total:
        lines.insert(1, "✅ ВСЕ подзадачи завершены (done/rejected/timed_out) — цель можно считать закрытой.")
    return "\n".join(lines)


async def main():
    import sys
    if len(sys.argv) > 1:
        goal_id = sys.argv[1]
        report = summarize_goal(goal_id)
        print(report)
        send_telegram_report(report)
        return

    open_ids = list_open_goal_ids()
    if not open_ids:
        print("Нет целей /goal с незавершёнными подзадачами сейчас.")
        return

    print(f"Незавершённых целей: {len(open_ids)}")
    reports = [summarize_goal(gid) for gid in open_ids]
    send_telegram_report("📋 ЕЖЕДНЕВНЫЙ СТАТУС ПО ЦЕЛЯМ /goal\n\n" + "\n\n".join(reports))


if __name__ == "__main__":
    asyncio.run(main())
