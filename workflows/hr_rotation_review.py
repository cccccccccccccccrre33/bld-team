"""
HR Rotation Review — периодический (раз в несколько недель) пересмотр
распределения специалистов по департаментам (agents/squads.py::SQUADS),
основанный на ФАКТИЧЕСКИХ исходах их задач (workflows/task_board.py::
get_specialist_stats()), а не на том, кто "давно не участвовал".

ЭТО НЕ ТО ЖЕ САМОЕ, ЧТО УЖЕ ЕСТЬ В КОДЕ:
- workflows/hr_checkin.py — тёплый личный разговор HR с одним случайным
  человеком про самочувствие. Не про штат, не меняет member_names.
- .state/squad_idle_rotation.json (workflows/_common.py::fair_sample) —
  честная очерёдность "кто говорит следующим" в обсуждениях. Тоже не
  про то, кто в каком департаменте состоит.

Раньше специалист вообще никогда не переезжал между member_names
разных департаментов — не было ни данных для решения (участие
трекалось, но не исход: done vs rejected vs timed_out), ни самого
механизма переноса.

Процесс:
1. get_specialist_stats() — у кого накопилось достаточно исходов.
2. Для тех, кто слабо выступает в СВОЁМ текущем департаменте (по
   member_names), но специфичнее совпадает по ключевым словам с ДРУГИМ
   — формулируем кандидата на перенос.
3. HR-агент оформляет это по-человечески одним сообщением в Telegram —
   явно как ПРЕДЛОЖЕНИЕ, ничего не меняя автоматически.
4. Применение — отдельный, осознанный шаг (apply_rotation), вызывается
   только явно (main_hr_rotation_review.py --apply "<имя>" "<департамент>"),
   никогда не как часть обычного review-прогона. Кадровое решение
   дороже багфикса — здесь сознательно нет self-approve ветки, в
   отличие от workflows/squad_initiative.py::is_minor_fix.
"""

import asyncio
import json
import subprocess
from pathlib import Path

from tools.telegram_report import send_telegram_report
from workflows.task_board import get_specialist_stats

# Меньше исходов — нечестно судить, это шум, не сигнал.
MIN_TASKS_FOR_SIGNAL = 3

# Ниже этой доли done/(done+rejected) — специалист "слабо выступает"
# в своём текущем департаменте (timed_out не участвует ни как успех,
# ни как провал — см. get_specialist_stats() docstring).
LOW_SUCCESS_THRESHOLD = 0.5


def compute_success_rate(stats: dict[str, int]) -> float | None:
    judged = stats["done"] + stats["rejected"]
    if judged < MIN_TASKS_FOR_SIGNAL:
        return None
    return stats["done"] / judged


def specialist_home_squad(name: str) -> str | None:
    """В member_names какого департамента сейчас числится специалист —
    None, если это не рядовой член департамента (лид, гильдия, роль
    вне SQUADS) — ротация в этом воркфлоу вообще не про них."""
    from agents.squads import SQUADS

    for key, squad in SQUADS.items():
        if name in squad["member_names"]:
            return key
    return None


def best_alternative_squad(name: str, current_key: str | None) -> tuple[str, int] | None:
    """Тот же принцип, что и workflows/big_projects.py::pick_relevant_group
    — общий словарь SPECIALTY_KEYWORDS всех модулей — но здесь ищем не
    людей под грань проекта, а департамент под личные ключевые слова
    человека. Возвращает (squad_key, overlap_score) для департамента с
    наибольшим совпадением, отличного от текущего, или None, если
    ничего не выделяется (у человека вообще нет личных ключевых слов
    в реестрах, или ни один чужой домен не пересекается)."""
    from agents.architecture_council import SPECIALTY_KEYWORDS as ARCH_KW
    from agents.engineering_fellows import SPECIALTY_KEYWORDS as FELLOW_KW
    from agents.expansion_geniuses import SPECIALTY_KEYWORDS as EXP_KW
    from agents.global_geniuses import SPECIALTY_KEYWORDS as GEN_KW
    from agents.growth_team import SPECIALTY_KEYWORDS as GROWTH_KW
    from agents.specialists import SPECIALTY_KEYWORDS as SPEC_KW
    from agents.squads import SQUADS

    all_kw = {**GEN_KW, **SPEC_KW, **GROWTH_KW, **EXP_KW, **ARCH_KW, **FELLOW_KW}
    personal_keywords = all_kw.get(name)
    if not personal_keywords:
        return None
    personal_text = " ".join(personal_keywords).lower()

    scores: dict[str, int] = {}
    for key, squad in SQUADS.items():
        if key == current_key:
            continue
        overlap = sum(1 for kw in squad["domain_keywords"] if kw in personal_text)
        if overlap:
            scores[key] = overlap
    if not scores:
        return None
    best_key = max(scores, key=scores.get)
    return best_key, scores[best_key]


async def review_rotation_candidates() -> list[dict]:
    """Собирает предложения на перенос — НИЧЕГО не меняет, только
    смотрит. Возвращает список dict: name, current_squad,
    suggested_squad, success_rate, task_count, overlap_score."""
    proposals = []
    for name, stats in get_specialist_stats().items():
        rate = compute_success_rate(stats)
        if rate is None or rate >= LOW_SUCCESS_THRESHOLD:
            continue
        current = specialist_home_squad(name)
        if current is None:
            continue
        alt = best_alternative_squad(name, current)
        if alt is None:
            continue
        suggested_key, overlap_score = alt
        proposals.append({
            "name": name,
            "current_squad": current,
            "suggested_squad": suggested_key,
            "success_rate": rate,
            "task_count": stats["done"] + stats["rejected"],
            "overlap_score": overlap_score,
        })
    return proposals


async def compile_rotation_report(proposals: list[dict]) -> str:
    from agents.executive_board import build_executive_board
    from agents.squads import SQUADS

    if not proposals:
        return (
            "🧑‍🤝‍🧑 HR Rotation Review\n\n"
            "Пересмотрел показатели по всем департаментам — сейчас нет ни одного "
            "специалиста, для кого накопилось достаточно данных (минимум "
            f"{MIN_TASKS_FOR_SIGNAL} завершённых задач) И кто явно слабее "
            "выступает не в своей зоне. Менять ничего не предлагаю."
        )

    hr_agent = build_executive_board()["hr"]

    raw_lines = [
        f"- {p['name']}: сейчас в {SQUADS[p['current_squad']]['label']}, "
        f"успех {p['success_rate'] * 100:.0f}% на {p['task_count']} завершённых задачах; "
        f"по ключевым словам специализации сильнее подходит "
        f"{SQUADS[p['suggested_squad']]['label']} (совпадение {p['overlap_score']} ключевых слов)."
        for p in proposals
    ]
    raw = "\n".join(raw_lines)

    prompt = f"""
Ты — HR. Раз в несколько недель ты пересматриваешь, кто в каком
департаменте числится — не по симпатиям, а по факту: где человек
реально успешен на задачах, и куда его специализация указывает
сильнее.

Вот сырые кандидаты на перенос (посчитано по факту задач на доске, не
твоё мнение с нуля):
{raw}

Сформулируй это для Валика по-человечески, не сухой таблицей — по
каждому кандидату короткий абзац: кто, почему предлагается перенос
(и успех, и совпадение специализации), и явно скажи, что это
ПРЕДЛОЖЕНИЕ, а не решение — Валик решает сам. Если кандидат один — без
вступления "вот несколько кандидатов", сразу по существу. В конце
одной строкой — как применить, если он согласен: команда
python main_hr_rotation_review.py --apply "<имя>" "<департамент>".
Без markdown-звёздочек, простой текст для Telegram.
"""
    response = await hr_agent.run(prompt)
    return response.text.strip()


def apply_rotation(name: str, target_squad_key: str) -> str:
    """Реально переносит специалиста в target_squad_key.

    НЕ редактирует agents/squads.py регулярным выражением напрямую —
    переписывать код на каждый перенос слишком рискованно (легко тихо
    сломать синтаксис файла с ~600 именами в списках). Вместо этого
    пишет решение в .state/squad_roster_overrides.json — читается и
    применяется на КАЖДОМ импорте agents/squads.py (см. там же,
    _apply_roster_overrides()) поверх статически объявленных
    member_names. Отдельный JSON-файл заодно даёт чистую историю
    решений в git-логе — что переносили и когда, а не диффы посреди
    полусотни других имён в squads.py.

    Вызывается ТОЛЬКО явно (main_hr_rotation_review.py --apply) —
    никогда не автоматически внутри review_rotation_candidates().
    """
    from agents.squads import SQUADS

    if target_squad_key not in SQUADS:
        return f"❌ Департамент '{target_squad_key}' не существует. Варианты: {', '.join(SQUADS.keys())}"

    current = specialist_home_squad(name)
    if current is None:
        return f"❌ '{name}' сейчас не числится ни в одном department member_names — переносить нечего."
    if current == target_squad_key:
        return f"⚠️ '{name}' уже в {SQUADS[target_squad_key]['label']} — переносить некуда."

    overrides_path = Path(".state/squad_roster_overrides.json")
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    overrides: dict[str, str] = {}
    if overrides_path.exists():
        try:
            overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
        except Exception:
            overrides = {}
    overrides[name] = target_squad_key
    overrides_path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", str(overrides_path)], check=True)
        result = subprocess.run(
            ["git", "commit", "-m", f"chore: ротация — {name} -> {target_squad_key}"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[hr_rotation_review] git push не удался (не критично для самого решения): {e}")

    return f"✅ '{name}' перенесён: {SQUADS[current]['label']} → {SQUADS[target_squad_key]['label']}."


async def main():
    import sys

    if len(sys.argv) >= 4 and sys.argv[1] == "--apply":
        name, target_squad_key = sys.argv[2], sys.argv[3]
        result = apply_rotation(name, target_squad_key)
        print(result)
        send_telegram_report(result)
        return

    print("Считаем статистику специалистов по доске задач...")
    proposals = await review_rotation_candidates()
    print(f"Кандидатов на перенос: {len(proposals)}")

    report = await compile_rotation_report(proposals)
    print(report)
    send_telegram_report(report)


if __name__ == "__main__":
    asyncio.run(main())
