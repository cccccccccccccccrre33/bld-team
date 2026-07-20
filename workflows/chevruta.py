"""
Хеврута — свободный формат парного/группового изучения (2-4 человека,
по образцу еврейской традиции совместного разбора текста). В отличие
от Лаборатории (workflows/lab_session.py, которая решает конкретную
проблему из кода) и от Squad Initiative/Individual Initiative (которые
идут к CTO ЗА ОДОБРЕНИЕМ на реализацию) — Хеврута не обязана быть
привязана к текущему коду или задаче вообще. Это исследование гипотезы
или идеи, "что если" — может быть про BLD System, а может быть чисто
техническое любопытство, которое потом даже не обязательно приведёт к
изменению кода.

Тон — позитивный, оптимистичный, но обдуманный: не "давайте писать
код прямо сейчас", а настоящее совместное мышление вслух, где идеи
можно пробовать, ошибаться, разворачивать в неожиданную сторону.

В конце группа сама решает, к кому пойти за реакцией — к "кумиру"
(случайно из CTO/CEO/Chief Scientist — те, кого молодые в компании
реально могли бы уважать) — тот смотрит и говорит: стоит копать
дальше, отдать в реализацию (тогда заводится задача на task board),
или просто интересная мысль, которая пока остаётся мыслью.
"""

import asyncio
import random

from agents.ceo import build_ceo
from agents.roster import build_full_roster
from agents.team import build_team
from tools.telegram_report import send_telegram_report
from workflows._common import compile_brief, curate_knowledge, fair_sample, record_participation, run_free_conversation, safe_agent_run, sync_repos_or_alert
from workflows.task_board import add_task

MAX_TURNS = 10  # чуть больше, чем в Лаборатории — это не решение задачи, а разговор

MENTOR_BUILDERS = {
    "cto": lambda: build_team()["cto"],
    "ceo": build_ceo,
}
MENTOR_LABELS = {"cto": "🧑‍💼 CTO", "ceo": "👑 CEO"}


def pick_group(roster: dict, size_hint: int | None = None) -> list[str]:
    """2-4 человека, с уклоном к меньшим группам (легче договориться) —
    смещено в пользу тех, кто дольше всех не участвовал НИГДЕ в
    компании (общий трекер fair_sample)."""
    size = size_hint or random.choices([2, 3, 4], weights=[45, 35, 20])[0]
    return fair_sample(list(roster.keys()), k=min(size, len(roster)))


async def spark_hypothesis(group_names: list[str], roster: dict) -> tuple[str, str]:
    """Один из группы (случайно) закидывает идею для совместного
    разбора — может быть про BLD, а может быть чисто техническое
    любопытство, не обязанное вести к немедленному изменению кода.

    Пробует по очереди КАЖДОГО из группы (не только первого), если у
    кого-то модель временно недоступна — не роняем всю хеврату.
    Возвращает (opener_name, text) — важно знать, кто реально
    высказался, а не всегда предполагать group_names[0]."""
    prompt_template = """
Ты начинаешь хевруту (свободный совместный разбор идеи) с коллегами:
{others}.

Закинь ОДНУ мысль/гипотезу/идею для совместного обдумывания — не
обязательно проблему из текущего кода, может быть техническое
любопытство, "а что если", наблюдение, которое давно вертелось в
голове. Тон — позитивный, живой, настоящий разговор коллег, а не
формальная постановка задачи. 2-4 предложения.
"""
    for opener_name in group_names:
        opener = roster[opener_name]
        others = ", ".join(n for n in group_names if n != opener_name)
        text = await safe_agent_run(opener, prompt_template.format(others=others), person_label=opener_name)
        if text is not None:
            return opener_name, text
    # Вся группа временно недоступна разом — статистически крайне
    # маловероятно, но на всякий случай не падаем, а сигнализируем None.
    return group_names[0], ""


async def find_mentor_reaction(topic: str, transcript_summary: str) -> tuple[str, str]:
    """Группа сама решает, к кому пойти — случайно из кумиров, но с
    учётом кто реально может дать содержательную реакцию на эту тему.
    Если у выбранного кумира модель временно недоступна — пробует
    оставшихся кумиров, прежде чем сдаться."""
    mentor_keys = list(MENTOR_BUILDERS.keys())
    random.shuffle(mentor_keys)
    for mentor_key in mentor_keys:
        mentor = MENTOR_BUILDERS[mentor_key]()
        label = MENTOR_LABELS[mentor_key]
        prompt = f"""
Группа коллег хевруты обсуждала: {topic}

Вот суть их разговора:
{transcript_summary}

Дай свою реакцию как {label.split()[-1]} — коротко и по существу:
стоит ли копать дальше, стоит ли отдать в реализацию (тогда явно
скажи "В РЕАЛИЗАЦИЮ" в начале ответа), или это просто интересная
мысль, которая пока не требует действий. Будь честным, но
поддерживающим — цель не отбить желание думать вслух, а дать
содержательный ориентир.
"""
        text = await safe_agent_run(mentor, prompt, person_label=mentor_key)
        if text is not None:
            return label, text
    return "🤷 (кумиры недоступны)", "Не удалось получить реакцию — все модели временно недоступны."


async def run_chevruta() -> str:
    roster = build_full_roster()
    group_names = pick_group(roster)
    record_participation(*group_names)
    print(f"Хеврута: {', '.join(group_names)}")

    opener_name, topic = await spark_hypothesis(group_names, roster)
    if not topic:
        msg = f"⚠️ Хеврута не состоялась — вся группа ({', '.join(group_names)}) временно недоступна."
        print(msg)
        send_telegram_report(msg)
        return msg
    print(f"\nТема ({opener_name}):\n{topic}\n{'=' * 60}")

    participants = [roster[n] for n in group_names]
    transcript = await run_free_conversation(participants, topic, max_turns=MAX_TURNS)

    lines = [f"{m.author_name}: {m.text.strip()}" for m in transcript]
    for line in lines:
        print(f"\n{line}")

    transcript_summary = "\n\n".join(lines)
    print(f"\n{'=' * 60}\nИдём за реакцией к кумиру...")
    mentor_label, reaction = await find_mentor_reaction(topic, transcript_summary)
    print(f"{mentor_label}: {reaction}")

    report = (
        f"📖 ХЕВРУТА — {', '.join(group_names)}\n\n"
        f"ТЕМА:\n{topic}\n\n"
        f"РАЗГОВОР:\n{transcript_summary[:2500]}\n\n"
        f"{mentor_label}:\n{reaction}"
    )
    brief = await compile_brief(report, context_hint="хеврута — свободное обсуждение в паре/тройке")
    send_telegram_report(brief)

    # Реакция кумира (CTO или CEO — MENTOR_BUILDERS) с "В РЕАЛИЗАЦИЮ" —
    # это САМО ПО СЕБЕ старшее одобрение, отдельного cto_approval() не
    # нужно (было бы избыточно спрашивать CTO дважды). Раньше на этом
    # всё заканчивалось — задача просто ложилась на task board и
    # реально никогда не реализовывалась, пока кто-то не подхватит её
    # руками. Теперь реализация запускается сразу.
    if "В РЕАЛИЗАЦИЮ" in reaction.upper():
        task_id = add_task(topic, "хеврута: " + "+".join(group_names), status="in_progress", reason=reaction)
        print(f"Заведена задача на доске: {task_id}. {mentor_label} одобрил — запускаем реализацию...")

        if not await sync_repos_or_alert():
            return report

        from workflows.engineering_task import run_engineering_task
        from workflows.task_board import update_task_status

        # ВАЖНО: как и в company_pulse/individual_initiative/squad_task/
        # lab_session/breakthrough_proposal/big_projects — оборачиваем в
        # try/except. Без этого необработанное исключение внутри
        # run_engineering_task() (таймаут модели, git-конфликт и т.п.)
        # оставляет задачу в "in_progress" НАВСЕГДА, что упирается в
        # MAX_CONCURRENT и молча блокирует реализацию во ВСЕХ остальных
        # воркфлоу компании, не только в хевруте.
        try:
            engineering_report = await run_engineering_task(topic)
        except Exception as e:
            print(f"[chevruta] run_engineering_task упал с исключением: {e}")
            update_task_status(task_id, "rejected", f"Упало с необработанным исключением: {e}")
            send_telegram_report(f"❌ Реализация по итогам хевруты ({', '.join(group_names)}) упала с ошибкой: {e}")
            return f"{report}\n\n❌ Реализация упала с ошибкой: {e}"

        update_task_status(task_id, "done")

        full = f"👷 РЕАЛИЗАЦИЯ ПО ИТОГАМ ХЕВРУТЫ ({mentor_label} одобрил)\n\n{engineering_report}"
        engineering_brief = await compile_brief(full, context_hint="реализация по итогам хевруты")
        send_telegram_report(engineering_brief)
        await curate_knowledge(f"Хеврута → реализовано: {', '.join(group_names)}", f"{report}\n\n{full}")
        return full
    await curate_knowledge(f"Хеврута: {', '.join(group_names)}", report)
    return report


async def main():
    await run_chevruta()


if __name__ == "__main__":
    asyncio.run(main())
