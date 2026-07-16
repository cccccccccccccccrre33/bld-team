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
from workflows._common import compile_brief, curate_knowledge
from workflows.task_board import add_task, get_board_summary, update_task_status

ESCALATION_MARKER = "ТРЕБУЕТ ТЕБЯ"


async def run_gtm_initiative() -> None:
    print(f"\n{'='*60}")
    print("[gtm] ИНИЦИАТИВА — GTM департамент")
    print(f"{'='*60}")

    # gtm-materials/ живёт в самом bld-team, но GTM Lead всё равно
    # синхронизирует bld-system/bld-panel как read-only контекст —
    # чтобы иметь актуальную картину продукта, о котором пишет.
    print(clone_or_update_repos())

    board_summary = get_board_summary()
    lead = build_gtm_lead()

    prompt = f"""
Текущая доска задач компании (контекст, не только твоя зона):
{board_summary}

Следуй своему процессу: посмотри, что уже есть в gtm-materials/, найди
ОДНУ конкретную полезную задачу прямо сейчас, сделай её через
write_gtm_doc, заверши текстовым резюме.
"""
    response = await lead.run(prompt)
    report_text = response.text.strip()

    needs_founder = ESCALATION_MARKER in report_text.upper() or ESCALATION_MARKER in report_text

    # Заголовок задачи для доски — первая содержательная строка резюме.
    title = next((line.strip() for line in report_text.split("\n") if line.strip()), "GTM: черновик документа")
    title = title[:120]

    task_id = add_task(
        title,
        "gtm",
        status="needs_founder_decision" if needs_founder else "done",
        reason="Автономная инициатива GTM-департамента.",
        how="Документ сохранён в gtm-materials/.",
    )
    if needs_founder:
        update_task_status(task_id, "needs_founder_decision")

    header = (
        "🧑‍💻 GTM: ЕСТЬ ПУНКТ, ТРЕБУЮЩИЙ ТВОЕГО РЕШЕНИЯ/ДЕЙСТВИЯ\n\n"
        if needs_founder
        else "📄 GTM: подготовлен черновик документа (самостоятельно, без действий вовне)\n\n"
    )
    full_report = header + report_text

    brief = await compile_brief(full_report)
    print(f"\n[ПОЛНЫЙ ОТЧЁТ]\n{full_report}")
    print(f"\n[КОРОТКО В TELEGRAM]\n{brief}")
    send_telegram_report(brief)
    await curate_knowledge("Инициатива: GTM", full_report)


async def main():
    await run_gtm_initiative()
