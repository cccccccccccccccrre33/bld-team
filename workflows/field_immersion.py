"""
Полевая практика — по прямому запросу Валика: "мне нужно много таких,
а не один [человек, который смотрит на систему глазами прораба] —
минимизировать людей, которые считай единственные в чём-либо
разбираются". Идея/разработка/дизайн/архитектура — в первую очередь
(его слова), но не только они.

ЧЕСТНО ПРО ГЛАВНОЕ ОГРАНИЧЕНИЕ (прочитать перед тем, как трогать этот
файл): на момент создания context/construction_domain.md — ЕДИНСТВЕННЫЙ
файл, где должны накапливаться реальные сырые наблюдения с площадки —
полностью пуст (каждый раздел буквально "пока пусто, ждёт реальных
данных от Валика"). Это значит, что field_to_product_designer и другие
"с опытом стройки" персоны в agents/construction_masters.py — вымышленные
композитные архетипы (как и весь остальной ростер, см. их собственный
докстринг), а не переработка реальных интервью. Плодить ещё десяток
таких же вымышленных биографий не решило бы запрос Валика "только по
реальности" — это просто больше вымысла, только шире.

ПОЭТОМУ этот модуль устроен так, что он ФИЗИЧЕСКИ НЕ МОЖЕТ ничего
выдумать вместо реальных данных: если в construction_domain.md ещё нет
ни одного заполненного раздела, run_immersion_session() не запускает ни
одного агента и не придумывает "правдоподобную" картину — вместо этого
шлёт Валику конкретный, а не общий запрос: какого именно раздела не
хватает и какой конкретно вопрос на него отвечает (см.
_ask_for_real_input()). Это осознанно спроектированный "тупик", а не
недоделка — тот же принцип, что "честно сказать 'не хватает данных'"
из самого construction_domain.md.

КАК ЭТО РЕАЛЬНО СПРАВЛЯЕТСЯ С "МИНИМИЗИРОВАТЬ ЕДИНСТВЕННЫХ ЭКСПЕРТОВ":
как только в construction_domain.md появляется хотя бы один реальный
раздел — session ротирует ШИРОКИЙ пул людей (Product/Alpha/Bravo/
Platform/Anomaly/NLU/QRA/Architecture Council/Research & Fundamentals —
т.е. именно "идеи/разработка/дизайн/архитектура" Валика, но не
construction_masters/construction_domain-гильдию — им бы это ничего не
дало, они и так уже про это) через ОТДЕЛЬНЫЙ трекер
(.state/field_immersion.json, не общий participation.json из
workflows/_common.py — нужен честный, отдельно видимый сигнал именно
по полевому пониманию, не смешанный с любым другим участием).
fair_sample() смещает выбор в пользу тех, кто реже всего (или вообще
ни разу) не проходил практику, и внутри одного человека — в пользу
раздела, который он ещё не читал. Через несколько недель прогонов
понимание физически размазано по десяткам разных людей с именами и
записями в личном дневнике (save_notebook_entry), а не сидит в одной
персоне — и это видно количественно через coverage_summary().

ЧТО ЭТО НЕ ЗАМЕНЯЕТ: это НЕ замена реальному Валику, физически
выезжающему на объект — это то, что происходит С РЕЗУЛЬТАТОМ такого
выезда ПОСЛЕ того, как он лёг в construction_domain.md. Сама культурная
норма "кто в компании отвечает за идеи/продукт/дизайн/архитектуру
регулярно бывает на объекте" — это про Валика как единственного живого
человека в компании (см. context/company_context.md, "Кто мы") и,
позже, про будущих реальных сотрудников, если они появятся — она
зафиксирована текстом там, не кодом здесь.
"""

import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from agents.architecture_council import ARCHITECT_BUILDERS
from agents.construction_masters import CONSTRUCTION_MASTERS_KEYS
from agents.global_elite_3 import ELITE_ROSTER_3
from agents.roster import build_full_roster
from agents.squads import SQUADS
from workflows._common import (
    curate_knowledge,
    fair_sample as _generic_fair_sample,
    notify_done,
    safe_agent_run,
    save_notebook_entry,
)
from workflows.product_backlog import add_entry
from tools.telegram_report import send_telegram_report

DOMAIN_FILE = Path("context/construction_domain.md")
STATE_DIR = Path(".state")
TRACKER_PATH = STATE_DIR / "field_immersion.json"

# Гильдия construction_domain (agents/guilds.py) — те же 10 из
# ELITE_ROSTER_3[60:70] + imperial_fluid_dynamics/som_load_bearing_engineer
# + 4 легенды мегапроектов. Их сюда включать бессмысленно — вся их
# специализация УЖЕ про реальность стройки, полевая практика ничего не
# добавит, только отнимет их редкое время у профильных задач.
_ALREADY_GROUNDED = {key for key, *_ in ELITE_ROSTER_3[60:70]} | {
    "imperial_fluid_dynamics", "som_load_bearing_engineer",
} | CONSTRUCTION_MASTERS_KEYS

# "особенно идеи разработка дизайн архитектура" — слова Валика. Идеи =
# Research & Fundamentals (гильдия, agents/guilds.py) + вообще все, кто
# предлагает инициативу; дизайн = Product; разработка = остальные 6
# отрядов; архитектура = Architecture Council. Приоритетный пул — не
# единственный (см. _eligible_pool: если приоритетного не хватает,
# используется весь общий ростер минус уже понимающие), но именно этим
# ролям достаётся основной вес практики.
_PRIORITY_KEYS: set[str] = set(ARCHITECT_BUILDERS.keys())
for _squad in SQUADS.values():
    _PRIORITY_KEYS.update(_squad.get("member_names", []))


def _load_tracker() -> dict:
    if not TRACKER_PATH.exists():
        return {}
    try:
        return json.loads(TRACKER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_tracker(data: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    TRACKER_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_domain_sections() -> dict[str, str]:
    """Разбирает construction_domain.md на {заголовок: контент},
    ОТБРАСЫВАЯ разделы-заглушки ("пока пусто..."). Считает раздел
    реальным, только если после заголовка есть непустой текст длиннее
    полутора строк-заглушки — грубая, но честная эвристика: лучше
    случайно пропустить короткий реальный раздел, чем случайно принять
    заглушку за реальные данные."""
    if not DOMAIN_FILE.exists():
        return {}
    text = DOMAIN_FILE.read_text(encoding="utf-8")
    sections = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    result = {}
    for block in sections:
        heading, _, body = block.partition("\n")
        body = body.strip()
        if len(body) < 80 or "пока пусто" in body.lower() or "ждёт" in body.lower()[:120]:
            continue
        result[heading.strip()] = body
    return result


def _eligible_pool() -> list[str]:
    roster = build_full_roster()
    priority = [n for n in roster if n in _PRIORITY_KEYS and n not in _ALREADY_GROUNDED]
    if len(priority) >= 3:
        return priority
    # Приоритетного пула не хватает (маленькая компания на старте,
    # или почти все уже практиковались недавно) — честно расширяем на
    # весь ростер минус тех, кому это точно не нужно, а не блокируем
    # практику целиком.
    return [n for n in roster if n not in _ALREADY_GROUNDED]


def _pick_unseen_section(name: str, sections: dict[str, str], tracker: dict) -> str:
    seen = set(tracker.get(name, {}).get("sections_covered", []))
    unseen = [h for h in sections if h not in seen]
    if unseen:
        return unseen[0]
    # Этот человек уже читал все существующие разделы — отдаём раздел,
    # который МЕНЬШЕ всего людей вообще читали (виден по tracker целиком),
    # чтобы понимание продолжало размазываться, а не концентрировалось.
    counts = {h: 0 for h in sections}
    for key, person_data in tracker.items():
        if key == "_last_nag":
            continue
        for h in person_data.get("sections_covered", []):
            counts[h] = counts.get(h, 0) + 1
    return min(counts, key=counts.get)


def _ask_for_real_input() -> None:
    """Единственное, что делает этот модуль, пока construction_domain.md
    пуст — конкретный, не расплывчатый запрос Валику, какие именно
    разделы заполнить и какой вопрос на них отвечает (сами вопросы —
    из шаблона самого construction_domain.md, не придуманы здесь).

    Троттлинг: не чаще раза в 3 дня — иначе, пока Валик не добавил
    данные, это превращается в ежедневный спам одним и тем же текстом,
    а не в полезный сигнал."""
    tracker = _load_tracker()
    last_nag = tracker.get("_last_nag", "")
    if last_nag:
        try:
            if (datetime.now() - datetime.fromisoformat(last_nag)).days < 3:
                return
        except Exception:
            pass

    if not DOMAIN_FILE.exists():
        send_telegram_report(
            "⚠️ Полевая практика не может начаться: файла "
            f"{DOMAIN_FILE} нет вообще. Без него все, кто должен "
            "понимать реальность площадки — только вымышленные "
            "архетипы."
        )
    else:
        text = DOMAIN_FILE.read_text(encoding="utf-8")
        headings = re.findall(r"^## (.+)$", text, flags=re.MULTILINE)
        send_telegram_report(
            "⚠️ Полевая практика не может начаться: context/construction_domain.md "
            f"пока пуст по всем {len(headings)} разделам. Нужны твои реальные "
            "наблюдения хотя бы по одному из них, чтобы много людей могли "
            "честно на них учиться, а не по одному вымышленному "
            f"'бывшему прорабу' в роcтере. Разделы: {', '.join(headings[:8])}"
            + ("…" if len(headings) > 8 else "")
        )

    tracker["_last_nag"] = datetime.now().isoformat()
    _save_tracker(tracker)


async def _immerse_one(name: str, person, section_title: str, section_text: str) -> dict | None:
    prompt = f"""
Тебе на разбор реальный (не вымышленный) фрагмент из наблюдений на
строительном объекте — раздел "{section_title}" из
context/construction_domain.md:

---
{section_text[:2500]}
---

Это ЕДИНСТВЕННЫЙ источник фактов, которым тебе разрешено пользоваться.
Не дополняй его своими вымышленными деталями, даже правдоподобными —
если чего-то не хватает, чтобы ответить на пункт ниже, так и напиши.

Ответь СТРОГО в этом формате:
СЦЕНА: [2-3 предложения — восстанови максимально конкретную физическую
картину: кто, где, с чем в руках, в каких условиях — только то, что
реально следует из текста выше]
БОЛЬ: [1-2 предложения — что тут объективно тяжело/тратит время/
раздражает человека на площадке, по тексту, не по общим соображениям]
ИДЕЯ: [1 предложение — одно конкретное, что можно автоматизировать/
оцифровать именно здесь; если текста недостаточно, чтобы предложить
что-то конкретное — напиши "НЕДОСТАТОЧНО ДАННЫХ" вместо идеи]
"""
    text = await safe_agent_run(person, prompt, person_label=name)
    if not text or len(text) < 20:
        return None
    result = {"name": name, "section": section_title}
    for line in text.split("\n"):
        up = line.upper()
        if up.startswith("СЦЕНА:"):
            result["scene"] = line.split(":", 1)[-1].strip()
        elif up.startswith("БОЛЬ:"):
            result["pain"] = line.split(":", 1)[-1].strip()
        elif up.startswith("ИДЕЯ:"):
            result["idea"] = line.split(":", 1)[-1].strip()
    if not result.get("scene"):
        return None
    return result


async def run_immersion_session(k: int = 3) -> None:
    sections = _parse_domain_sections()
    if not sections:
        _ask_for_real_input()
        return

    tracker = _load_tracker()
    pool = _eligible_pool()
    if not pool:
        print("[field_immersion] Пул пуст — все либо уже глубоко в теме, либо ростер ещё мал.")
        return

    # Собственный трекер практики, не общий participation.json — честный,
    # отдельно видимый сигнал именно по полевому пониманию (см. докстринг).
    stale_order = sorted(pool, key=lambda n: tracker.get(n, {}).get("last", ""))
    chosen = _generic_fair_sample(stale_order[: max(k * 4, k)], k=k, fairness=0.8)

    roster = build_full_roster()
    results = []
    for name in chosen:
        section_title = _pick_unseen_section(name, sections, tracker)
        result = await _immerse_one(name, roster[name], section_title, sections[section_title])
        if result is None:
            continue
        results.append(result)

        entry_text = (
            f"[{section_title}] Сцена: {result.get('scene', '')} "
            f"Боль: {result.get('pain', '')} Идея: {result.get('idea', '')}"
        )
        save_notebook_entry(name, f"Полевая практика — {entry_text}")

        if result.get("idea") and "НЕДОСТАТОЧНО ДАННЫХ" not in result["idea"].upper():
            add_entry(
                title=result["idea"],
                summary=f"Найдено при полевой практике ({section_title}): {result.get('pain', '')}",
                origin="field_immersion",
                scope="крупное",
                participants=[name],
            )

        tracker.setdefault(name, {"sections_covered": []})
        if section_title not in tracker[name]["sections_covered"]:
            tracker[name]["sections_covered"].append(section_title)
        tracker[name]["last"] = datetime.now().isoformat()

    _save_tracker(tracker)

    if results:
        digest = "; ".join(f"{r['name']}→{r['section']}" for r in results)
        await curate_knowledge(
            "field_immersion",
            f"Полевая практика: {digest}. Полные записи — в личных дневниках "
            "участников и в бэклоге идей (origin=field_immersion).",
        )
        notify_done(
            "Полевая практика проведена",
            f"{len(results)} человек прошли практику: {', '.join(r['name'] for r in results)}",
        )


def coverage_summary() -> str:
    """Сколько разных людей реально прошли практику и по каким разделам —
    прямой количественный ответ на 'минимизировать единственных
    экспертов': если тут один человек и один раздел — задача ещё не
    решена, сколько бы персон с красивыми биографиями ни было в ростере."""
    tracker = _load_tracker()
    sections = _parse_domain_sections()
    if not sections:
        return "Полевая практика ещё не может идти — construction_domain.md пуст."
    lines = [f"Разделов с реальными данными: {len(sections)}"]
    person_entries = {k: v for k, v in tracker.items() if k != "_last_nag"}
    lines.append(f"Людей прошло практику хотя бы раз: {len(person_entries)}")
    per_section: dict[str, int] = {h: 0 for h in sections}
    for data in person_entries.values():
        for h in data.get("sections_covered", []):
            per_section[h] = per_section.get(h, 0) + 1
    for h, count in sorted(per_section.items(), key=lambda kv: kv[1]):
        flag = " ⚠️ единственный человек" if count == 1 else ""
        lines.append(f"  {h}: {count} человек(а){flag}")
    return "\n".join(lines)


async def main():
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    await run_immersion_session(k=k)


if __name__ == "__main__":
    asyncio.run(main())
