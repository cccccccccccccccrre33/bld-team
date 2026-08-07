"""
Инициатива GTM-департамента — независимый цикл по образцу
workflows/squad_initiative.py, но с другим итогом работы: не код в
bld-system/bld-panel, а markdown-документы в gtm-materials/ (см.
agents/gtm.py про причину такого ограничения).

Запускается реже инженерных отрядов (см. .github/workflows/
gtm_initiative.yml) — материалы полезны, только если Валик успевает их
реально использовать между запусками, штамповать черновики впрок
бессмысленно.
"""

from agents.gtm import build_gtm_lead
from tools.repo_tools import clone_or_update_repos
from tools.telegram_report import send_telegram_report
from workflows._common import curate_knowledge, notify_done, record_participation
from workflows.task_board import add_task, get_board_summary, update_task_status

ESCALATION_MARKER = "ТРЕБУЕТ ТЕБЯ"


async def run_gtm_initiative(task_hint: str | None = None, goal_id: str | None = None) -> None:
    """task_hint/goal_id — опционально, оба default None (старое
    поведение по расписанию не меняется вообще). Добавлены, чтобы
    workflows/goal_intake.py (/goal) могло передать сюда реальный текст
    цели вместо того, чтобы GTM Lead каждый раз сам придумывал тему с
    нуля — раньше эта функция вообще не принимала никакого входного
    сигнала, кроме доски задач."""
    print(f"\n{'='*60}")
    print("[gtm] ИНИЦИАТИВА — GTM департамент")
    print(f"{'='*60}")

    # gtm-materials/ живёт в самом bld-team, но GTM Lead всё равно
    # синхронизирует bld-system/bld-panel как read-only контекст —
    # чтобы иметь актуальную картину продукта, о котором пишет.
    print(clone_or_update_repos())

    board_summary = get_board_summary()
    lead = build_gtm_lead()

    hint_block = (
        f"\nКонкретный запрос, с которым стоит начать (направление, не обязательно "
        f"дословная формулировка задачи для доски): {task_hint}\n"
        if task_hint else ""
    )

    prompt = f"""
Текущая доска задач компании (контекст, не только твоя зона):
{board_summary}
{hint_block}
Следуй своему процессу: посмотри, что уже есть в gtm-materials/, найди
ОДНУ конкретную полезную задачу прямо сейчас, сделай её через
write_gtm_doc, заверши текстовым резюме.
"""
    response = await lead.run(prompt)
    report_text = response.text.strip()
    record_participation(lead.name)

    needs_founder = ESCALATION_MARKER in report_text.upper() or ESCALATION_MARKER in report_text

    # Заголовок задачи для доски — первая содержательная строка резюме.
    title = next((line.strip() for line in report_text.split("\n") if line.strip()), "GTM: черновик документа")
    title = title[:120]

    task_id = add_task(
        title,
        "gtm",
        status="needs_founder_decision" if needs_founder else "done",
        reason="Автономная инициатива GTM-департамента." if not task_hint else f"Инициировано через /goal: {task_hint}",
        how="Документ сохранён в gtm-materials/.",
        goal_id=goal_id,
    )
    if needs_founder:
        update_task_status(task_id, "needs_founder_decision")

    header = (
        "🧑‍💻 GTM: ЕСТЬ ПУНКТ, ТРЕБУЮЩИЙ ТВОЕГО РЕШЕНИЯ/ДЕЙСТВИЯ\n\n"
        if needs_founder
        else "📄 GTM: подготовлен черновик документа (самостоятельно, без действий вовне)\n\n"
    )
    full_report = header + report_text

    print(f"\n[ПОЛНЫЙ ОТЧЁТ]\n{full_report}")
    if needs_founder:
        send_telegram_report(f"🧑‍💻 GTM — требует твоего решения: {title}")
    else:
        notify_done(f"GTM: {title}")
    await curate_knowledge("Инициатива: GTM", full_report)


async def main():
    await run_gtm_initiative()
