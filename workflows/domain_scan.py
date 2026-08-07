"""
Domain Scan — по прямому запросу Валика: "хочу чтобы все в компании
работали, вообще все чем-то были заняты в своей сфере", а не только
те ~20-30 человек, кому в моменте повезло попасть в fair_sample() в
одном из десятка независимых cron-воркфлоу.

ЧТО ЭТО НЕ ДЕЛАЕТ (осознанно):
- НЕ читает код (никакого git_log/grep_repo) — это не замена
  individual_initiative.py::scout_and_propose, а более дешёвый и
  широкий слой ПЕРЕД ним. scout_and_propose даёт обоснованное решение
  на реальном коде для конкретного человека несколько раз в день;
  domain_scan даёт поверхностный взгляд, но на ВСЮ компанию раз в день.
- НЕ пишет в git, НЕ создаёт задачи на task board, НЕ имеет
  self-approve. Всё, что здесь найдено, уходит ТОЛЬКО в
  workflows/product_backlog.py. Причина: у scout_and_propose уверенность
  обоснована чтением реального кода, здесь — нет, пускать необоснованные
  находки сразу в self_approved (см. individual_initiative.py про
  "уверен = сам берёт в работу без согласования") было бы понижением
  качества входа в тот же самый пайплайн, которому Валик как раз
  доверил решать самому. Roster здесь строится с can_write=False
  везде — не случайно, тот же принцип, что и у agents/roster.py для
  discussion-ролей.
- НЕ гоняет 612 запросов одним asyncio.gather. Даже с дешёвыми
  моделями это реальный риск словить rate limit у сторонних
  провайдеров разом (см. config/models.py — квота ~4 запроса у
  стороннего провайдера против 800 у gpt-моделей). Здесь — семафор per
  provider family (см. _semaphore_for) внутри процесса. ВАЖНО: это
  ограничивает конкурентность ВНУТРИ одного шарда/процесса, а не
  между параллельными GitHub Actions раннерами матрицы — если шардов
  запущено много одновременно, они всё равно не знают друг о друге.
  Это НЕ решено полностью здесь — оставлено на safe_agent_run() (ретраи
  с паузой) как второй рубеж, и на разумное число шардов в самом yml,
  а не тысячу одновременных раннеров.

ЧТО ЭТО ДАЁТ:
- Гарантированное покрытие: роster делится ДЕТЕРМИНИРОВАННО (slice по
  индексу), не через fair_sample — то есть за один полный прогон всех
  шардов действительно охвачены ВСЕ, а не "у кого-то есть шанс".
- Каждый видит, не лежит ли уже в бэклоге что-то по его теме, ещё
  никем не подхваченное (get_pull_candidate) — так бэклог реально
  вычерпывается, а не только растёт.
"""

import asyncio
import os
import sys
from pathlib import Path

import config.models as _models_config
from agents.roster import build_full_roster
from config.client_factory import _GPT_FAMILY_PREFIXES
from workflows._common import safe_agent_run
from workflows.individual_initiative import ALL_MATCH_KEYWORDS
from workflows.product_backlog import add_entry, get_pull_candidate, mark_pulled

# Единая карта role_key -> deployment name, собранная из ВСЕХ словарей
# *_MODEL_ASSIGNMENTS в config/models.py — динамически, а не построчным
# перечислением всех 16 словарей, чтобы не рассинхронизироваться при
# следующем расширении ростера (та же логика, что в
# individual_initiative.py про пересчёт "586" по факту содержимого
# словарей, а не по старой захардкоженной цифре).
_ROLE_MODEL_MAP: dict[str, str] = {}
for _attr_name in dir(_models_config):
    if _attr_name.endswith("_MODEL_ASSIGNMENTS"):
        _ROLE_MODEL_MAP.update(getattr(_models_config, _attr_name))

# С запасом ниже реальной квоты стороннего провайдера (~4 RPM, см.
# config/models.py) — даже если несколько ролей на одном и том же
# провайдере совпадут по времени внутри одного шарда.
_THIRD_PARTY_CONCURRENCY = 3
_AZURE_OPENAI_CONCURRENCY = 15
_provider_semaphores: dict[str, asyncio.Semaphore] = {}


def _provider_family(model_name: str) -> str:
    """Та же граница, что client_factory.py использует для выбора
    FoundryChatClient (Azure OpenAI) vs Model Inference API (сторонний
    marketplace) — переиспользуем её же константу, не изобретаем
    вторую классификацию, которая рано или поздно разъедется с первой."""
    if model_name.startswith(_GPT_FAMILY_PREFIXES):
        return "azure_openai"
    return f"third_party:{model_name.split('-')[0].lower()}"


def _semaphore_for(role_key: str) -> asyncio.Semaphore:
    model_name = _ROLE_MODEL_MAP.get(role_key, "")
    family = _provider_family(model_name) if model_name else "unknown"
    if family not in _provider_semaphores:
        limit = _AZURE_OPENAI_CONCURRENCY if family == "azure_openai" else _THIRD_PARTY_CONCURRENCY
        _provider_semaphores[family] = asyncio.Semaphore(limit)
    return _provider_semaphores[family]


def _shard_names(all_names: list[str], shard_index: int, shard_count: int) -> list[str]:
    """Детерминированный срез (не fair_sample!) — сортируем имена один
    раз, чтобы срез был стабильным между шардами одного прогона, и
    берём slice по индексу. За N шардов при shard_count=N это ровно
    100% ростера, без пересечений и без пропусков."""
    ordered = sorted(all_names)
    return ordered[shard_index::shard_count]


async def scan_one(name: str, person) -> dict | None:
    """Один дешёвый прогон без tools. Возвращает найденную идею или
    None ('нечего добавить' — это нормальный, ожидаемый исход для
    большинства людей в большинство дней, не ошибка)."""
    personal_keywords = ALL_MATCH_KEYWORDS.get(name, [])
    pull_hint = ""
    candidate = get_pull_candidate(personal_keywords) if personal_keywords else None
    if candidate:
        pull_hint = (
            f"\n\nВ общем бэклоге уже лежит идея по твоей теме, никем ещё не "
            f"подхваченная: \"{candidate['title']}\" — {candidate['summary'][:200]}\n"
            f"Можешь опереться на неё вместо того, чтобы придумывать с нуля, "
            f"или сказать своё, если видишь другое."
        )
        mark_pulled(candidate["id"])

    prompt = f"""
Быстрый взгляд на свою область в BLD System/BLD Panel — без похода в
код, просто по тому, что ты уже знаешь о своей зоне ответственности:
что сейчас реально стоило бы сделать лучше?{pull_hint}

Если сходу ничего конкретного не видишь — это нормально, ответь
строго: НЕЧЕГО ДОБАВИТЬ

Если видишь — ответь СТРОГО в этом формате:
ИДЕЯ: [одна строка]
ПОЧЕМУ: [1-2 предложения]
МАСШТАБ: МЕЛКОЕ или КРУПНОЕ
(МЕЛКОЕ — можно пробовать реализовать буквально сегодня; КРУПНОЕ —
стоит сначала обдумать/обсудить, не для сиюминутной реализации)
"""
    sem = _semaphore_for(name)
    async with sem:
        text = await safe_agent_run(person, prompt, person_label=name)

    if not text or "НЕЧЕГО ДОБАВИТЬ" in text.upper() or len(text) < 15:
        return None

    result = {"name": name}
    for line in text.split("\n"):
        up = line.upper()
        if up.startswith("ИДЕЯ:"):
            result["title"] = line.split(":", 1)[-1].strip()
        elif up.startswith("ПОЧЕМУ:"):
            result["reason"] = line.split(":", 1)[-1].strip()
        elif up.startswith("МАСШТАБ:"):
            result["scope"] = "мелкое" if "МЕЛКОЕ" in up else "крупное"

    if not result.get("title"):
        return None
    result.setdefault("reason", "")
    result.setdefault("scope", "неизвестно")
    return result


async def run_shard(shard_index: int, shard_count: int) -> None:
    roster = build_full_roster()
    names = _shard_names(list(roster.keys()), shard_index, shard_count)
    print(f"[domain_scan] Шард {shard_index}/{shard_count}: {len(names)} человек из {len(roster)}")

    results = await asyncio.gather(
        *(scan_one(n, roster[n]) for n in names),
        return_exceptions=True,
    )

    found = 0
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            print(f"[domain_scan] {name} упал с исключением: {result}")
            continue
        if result is None:
            continue
        found += 1
        add_entry(
            title=result["title"],
            summary=result["reason"],
            origin="domain_scan",
            scope=result["scope"],
            participants=[name],
        )

    summary = (
        f"[domain_scan] Шард {shard_index}/{shard_count}: "
        f"просканировано {len(names)}, новых идей в бэклоге: {found}"
    )
    print(summary)
    # РАНЬШЕ каждый шард слал отчёт в Telegram — убрано по запросу
    # Валика: это не готовая работа, а ежедневный обзор. 6 шардов x
    # такое сообщение = 6 уведомлений в день ни о чём конкретном.
    # Сами найденные идеи — в product_backlog.py, видно через
    # format_summary()/backlog_pressure(), не потеряны.


async def main():
    shard_index = int(os.getenv("SHARD_INDEX", sys.argv[1] if len(sys.argv) > 1 else "0"))
    shard_count = int(os.getenv("SHARD_COUNT", sys.argv[2] if len(sys.argv) > 2 else "1"))
    await run_shard(shard_index, shard_count)


if __name__ == "__main__":
    asyncio.run(main())
