"""
"20% времени" — переиспользуемый механизм крупных проектов "с нуля"
(в духе Google 20% time), но не размазанный тонким слоем по неделе, а
сконцентрированный в ОДИН интенсивный день (например, пятницу) — в
этот день компания много раз за день возвращается к проекту (каждый
час), создавая ощущение непрерывной стройки, хотя технически это
серия отдельных запусков (GitHub Actions не умеет держать процесс
живым буквально сутки).

Реестр (.state/projects/{project_id}.json) — универсальная структура,
можно добавлять новые крупные проекты, не только "сезонный режим",
который был первым. У каждого проекта:
- brief — исходное описание/бриф (то, что дал Валик).
- phase — DIGEST (осмысление) -> DESIGN (варианты и дизайн-решения) ->
  APPROVAL (лёгкая бюрократия — согласование) -> IMPLEMENTATION
  (реализация по частям, может затрагивать и bld-system, и bld-panel —
  в отличие от Fellows, этот механизм НЕ ограничен одним репозиторием)
  -> DONE.
- log — накопленная история обсуждений/решений по фазам.
- decisions — зафиксированные дизайн-решения (что решили и почему).

За один "рабочий день" проекта происходит НЕСКОЛЬКО параллельных
кластеров обсуждения (как в Company Pulse) — разные грани одного
проекта одновременно (например, один кластер обсуждает UI/UX
переключателя, другой — как считать "итоги сезона" по L1-L9,
третий — бизнес-обоснование удержания клиентов зимой), не один
последовательный разговор.

Участники подбираются НЕ чисто случайно — а по совпадению фазы/грани
проекта с реальной специализацией (тот же принцип, что и консультации
в individual_initiative.py), плюс fair_sample для отсутствия перекоса.
"""

import asyncio
import json
import subprocess
from datetime import datetime
from pathlib import Path

from agents.roster import build_full_roster
from agents.team import build_team
from config.client_factory import get_chat_client
from config.models import BOARD_MODEL_ASSIGNMENTS
from tools.telegram_report import send_telegram_report
from workflows._common import ask, curate_knowledge, fair_sample, record_participation, run_free_conversation, sync_repos_or_alert
from workflows.cto_approval import cto_approval
from workflows.task_board import add_task, is_duplicate, update_task_status

STATE_DIR = Path(".state")
PROJECTS_DIR = STATE_DIR / "projects"

PHASES = ["DIGEST", "DESIGN", "APPROVAL", "IMPLEMENTATION", "DONE"]

# Реестр проектов "20% времени" — сюда можно дописывать новые крупные
# проекты в будущем, не трогая остальной механизм. Каждый проект несёт
# исходный бриф (то, что реально сказал Валик) и подсказки по граням
# для подбора релевантных участников на разных фазах.
PROJECTS_REGISTRY = {
    "seasonal_mode": {
        "title": "Сезонный режим BLD System (пик стройки vs межсезонье)",
        "brief": """
Пик строительства — с середины весны по середину осени. Задача: как
удерживать клиентов круглый год, чтобы каждый сезон не искать новых
платящих заново.

Идея (черновая, можно и нужно дорабатывать): вне пикового сезона
продукт меняет функцию — не "контроль стройки в моменте", а
"подготовка и итоги": разбор прошлого сезона (перерасходы, какие
бригады подвели — используя те же L1-L9 данные), планирование бюджета
следующего года на основе истории, закрытие документов/актов/гарантий.
Идея в том, чтобы удержать привычку открывать приложение даже когда
объект не строится.

Варианты реализации, которые можно рассмотреть (это лишь примеры для
затравки, решение — за командой): переключатель/режим системы вне пика;
блокировка обычного функционала вне сезона в пользу "зимнего" режима;
просто отдельная вкладка "Итоги сезона / Планирование", доступная
всегда, без блокировки основного функционала.

Обоснование из поведенческой экономики (для контекста, не как
готовое решение): подписочные сервисы, дающие опцию "пауза" вместо
отмены, конвертируют 10-20% попыток отмены в паузу, снижают churn
и поднимают LTV — работает через loss aversion, status quo bias,
sunk-cost effect. У сезонных подрядчиков (ландшафтный/сервисный
бизнес) клиенты, пользующиеся сервисом и летом, и зимой, уходят
значительно реже — переключение на конкурента означает искать замену
сразу для двух use case, а не для одного. Важный нюанс: "зимний"
режим должен ощущаться как забота о клиенте, а не как ловушка,
удерживающая силой — это вопрос UX-копирайтинга и реального удобства,
не просто механика удержания.

Задача команды: сначала полностью осмыслить эту идею, обсудить и
предложить лучший вариант реализации (может быть не из перечисленных
выше, а свой), пройти лёгкое согласование (архитектура + бизнес-
ценность + дизайн), и затем реализовать — как минимум MVP-версию.
""",
        "facets": [
            ("ui_ux_design", "как это должно выглядеть и ощущаться для владельца/менеджера — переключатель, отдельная вкладка, или другой UX",
             ["ux", "интерфейс", "дизайн", "вкладк", "переключател"]),
            ("data_reuse", "как переиспользовать L1-L9 данные anomaly engine для 'итогов сезона' и планирования бюджета",
             ["anomaly", "аномал", "l1", "l9", "статистик", "калибровк", "данн"]),
            ("business_retention", "бизнес-обоснование и модель удержания клиента через межсезонье",
             ["удержан", "churn", "retention", "подписк", "бизнес-модель"]),
            ("data_bootstrapping", "у BLD пока НЕТ достаточной собственной истории по объектам/компаниям для "
             "обучения ML — нужно продумать: действительно ли нужен ML на старте этой фичи, или достаточно "
             "простой статистики/правил на имеющихся данных; если ML всё же нужен — как получить обучающие "
             "данные ДО накопления реальной истории (синтетические данные, максимально правдоподобные и "
             "приближенные к реальным паттернам строительных объектов, а не выдуманные наугад) и как потом "
             "плавно заменить синтетику реальными данными по мере накопления",
             ["обучени", "ml модель", "синтетическ", "историческ данн", "недостаточно данных", "training data"]),
        ],
    },
}


def project_path(project_id: str) -> Path:
    return PROJECTS_DIR / f"{project_id}.json"


def load_project(project_id: str) -> dict:
    """РАНЬШЕ brief/facets НИКОГДА не сохранялись в сам JSON проекта —
    их всегда читали заново из PROJECTS_REGISTRY (см. ниже по файлу,
    было PROJECTS_REGISTRY[project['id']]['brief'] и
    PROJECTS_REGISTRY[project_id]["facets"]). Это значило, что
    ЕДИНСТВЕННЫЙ способ завести новый проект — вручную дописать запись
    в этот статический словарь в коде и закоммитить: даже если совет
    директоров или обсуждение в Company Pulse решали, что нужен новый
    крупный проект, идея просто терялась, пока кто-то (Валик) не
    вспоминал и не правил код руками.

    ТЕПЕРЬ brief и facets — часть самого сохранённого dict проекта
    (пишутся при создании, см. register_project() ниже) — так что
    новый проект можно завести ПОЛНОСТЬЮ в рантайме, без правки кода.
    PROJECTS_REGISTRY остаётся как есть — легаси-путь для проектов,
    у которых ещё нет файла на диске (первый запуск), не единственный
    путь регистрации."""
    path = project_path(project_id)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Старые файлы, сохранённые ДО этого изменения, не содержат
            # brief/facets — на этот случай подстраховываемся легаси-
            # реестром, если запись там есть (для seasonal_mode и
            # подобных — так избегаем KeyError на уже накопленном
            # прогрессе существующих проектов).
            if "brief" not in data or "facets" not in data:
                legacy = PROJECTS_REGISTRY.get(project_id, {})
                data.setdefault("brief", legacy.get("brief", ""))
                data.setdefault("facets", legacy.get("facets", []))
            return data
        except Exception:
            pass
    if project_id not in PROJECTS_REGISTRY:
        raise KeyError(
            f"Проект '{project_id}' не найден ни в .state/projects/, ни в PROJECTS_REGISTRY — "
            "используй register_project() для регистрации нового проекта, а не load_project() напрямую."
        )
    reg = PROJECTS_REGISTRY[project_id]
    return {
        "id": project_id,
        "title": reg["title"],
        "brief": reg["brief"],
        "facets": reg["facets"],
        "phase": "DIGEST",
        "log": [],
        "decisions": [],
        "created": datetime.now().isoformat(),
    }


def save_project(project: dict) -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    project_path(project["id"]).write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", str(project_path(project["id"]))], check=True)
        result = subprocess.run(
            ["git", "commit", "-m", f"chore: проект '{project['id']}' — обновление"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[big_projects] Не удалось сохранить проект в git: {e}")


def format_log(log: list[dict], limit: int = 25) -> str:
    if not log:
        return "(пока ничего не обсуждалось — это первая сессия по проекту)"
    return "\n".join(f"[{e['date']}] {e['who']}: {e['text']}" for e in log[-limit:])


def pick_relevant_group(roster: dict, keywords: list[str], k: int = 3) -> list[str]:
    """Ищет людей, чья специализация (по общим SPECIALTY_KEYWORDS всех
    модулей) совпадает с гранью проекта, плюс честно добирает
    остальных через fair_sample, если совпадений меньше k."""
    from agents.architecture_council import SPECIALTY_KEYWORDS as ARCH_KW
    from agents.engineering_fellows import SPECIALTY_KEYWORDS as FELLOW_KW
    from agents.expansion_geniuses import SPECIALTY_KEYWORDS as EXP_KW
    from agents.global_geniuses import SPECIALTY_KEYWORDS as GEN_KW
    from agents.growth_team import SPECIALTY_KEYWORDS as GROWTH_KW
    from agents.specialists import SPECIALTY_KEYWORDS as SPEC_KW

    all_kw = {**GEN_KW, **SPEC_KW, **GROWTH_KW, **EXP_KW, **ARCH_KW, **FELLOW_KW}
    matched = [name for name, kws in all_kw.items() if name in roster and any(kw in " ".join(keywords).lower() for kw in kws)]

    if len(matched) >= k:
        return fair_sample(matched, k=k)
    rest = [n for n in roster if n not in matched]
    extra = fair_sample(rest, k=k - len(matched)) if rest else []
    return matched + extra


async def run_facet_cluster(project: dict, facet_key: str, facet_desc: str, facet_keywords: list[str], roster: dict) -> None:
    """Один кластер обсуждения — конкретная грань проекта, отдельная
    небольшая группа (2-3 человека), результат дописывается в общий
    лог проекта."""
    group_names = pick_relevant_group(roster, facet_keywords, k=3)
    record_participation(*group_names)
    participants = [roster[n] for n in group_names]

    recent_log = format_log(project["log"])
    opening = f"""
Проект: {project['title']} (фаза: {project['phase']})

Бриф проекта:
{project['brief']}

Что уже обсуждалось в проекте (весь проект, не только эта грань):
{recent_log}

Твоя группа сегодня фокусируется именно на грани: {facet_desc}.
Обсудите это между собой — конкретно, по существу, с вариантами и
аргументами за/против. Если фаза проекта DESIGN — предложите
конкретное дизайн-решение по своей грани. Если IMPLEMENTATION —
обсудите, как технически это сделать.
"""
    transcript = await run_free_conversation(participants, opening, max_turns=6)

    for m in transcript:
        project["log"].append({
            "date": datetime.now().strftime("%d.%m %H:%M"),
            "who": f"{m.author_name} [{facet_key}]",
            "text": m.text.strip()[:500],
        })

    summary_lines = "\n".join(f"{m.author_name}: {m.text.strip()}" for m in transcript)
    send_telegram_report(f"🏗️  {project['title']} — грань «{facet_desc}»\n\n{summary_lines}")


async def assess_phase_transition(project: dict) -> str | None:
    """Проверяет, готова ли текущая фаза перейти к следующей — по
    совокупности накопленного лога, не по одной реплике."""
    client = get_chat_client(BOARD_MODEL_ASSIGNMENTS.get("agenda_setter", "gpt-5.2"))
    log_text = format_log(project["log"], limit=40)

    idx = PHASES.index(project["phase"])
    if idx >= len(PHASES) - 1:
        return None
    next_phase = PHASES[idx + 1]

    prompt = f"""
Проект: {project['title']}
Текущая фаза: {project['phase']}
Следующая фаза: {next_phase}

Накопленное обсуждение:
{log_text}

Готова ли фаза {project['phase']} к переходу в {next_phase}? Для
DIGEST->DESIGN: команда реально осмыслила бриф и начала предлагать
варианты. Для DESIGN->APPROVAL: есть конкретное дизайн-решение (не
несколько равнозначных вариантов без выбора). Для APPROVAL-
>IMPLEMENTATION: получено согласование. Для IMPLEMENTATION->DONE: все
запланированные части реализованы.

Ответь строго: ГОТОВО: ДА или ГОТОВО: НЕТ
Если ДА, одной строкой: ИТОГ: [что именно решено/готово]
"""
    response = await ask(client, prompt)
    if "ГОТОВО: ДА" not in response.upper():
        return None

    summary = ""
    for line in response.split("\n"):
        if line.upper().startswith("ИТОГ:"):
            summary = line.split(":", 1)[-1].strip()
            break

    project["decisions"].append({"phase_completed": project["phase"], "summary": summary, "date": datetime.now().isoformat()})
    project["phase"] = next_phase
    return summary


async def run_project_day(project_id: str) -> None:
    """Один тик рабочего дня проекта — несколько параллельных
    кластеров по разным граням, затем проверка перехода фазы, и (если
    дошли до IMPLEMENTATION) реальная реализация конкретных частей."""
    if not await sync_repos_or_alert():
        return

    project = load_project(project_id)
    if project["phase"] == "DONE":
        print(f"[{project_id}] Проект уже завершён.")
        return

    roster = build_full_roster()
    facets = project["facets"]

    print(f"[{project_id}] Фаза {project['phase']} — запускаем {len(facets)} параллельных кластеров...")
    await asyncio.gather(*[
        run_facet_cluster(project, key, desc, kws, roster) for key, desc, kws in facets
    ])

    save_project(project)

    transition_summary = await assess_phase_transition(project)
    if transition_summary:
        # КРИТИЧНО: assess_phase_transition() уже изменил project["phase"]
        # и дописал в project["decisions"] — но save_project() выше был
        # вызван ДО этого. Если не сохранить прямо здесь, переход фазы
        # (например DIGEST->DESIGN) существует только в памяти этого
        # тика и теряется навсегда: следующий запуск загрузит с диска
        # старую фазу и повторит то же самое обсуждение заново — отсюда
        # эффект "вечного перехода в DESIGN", который никогда не доходит
        # до APPROVAL/IMPLEMENTATION.
        save_project(project)
        send_telegram_report(f"✅ {project['title']} — фаза завершена: {transition_summary}\nПереход к фазе {project['phase']}.")
        await curate_knowledge(f"Проект {project_id}: фаза завершена", transition_summary)

        if project["phase"] == "APPROVAL":
            print(f"[{project_id}] Лёгкое согласование — CTO...")
            design_summary = "\n".join(d["summary"] for d in project["decisions"])
            approved, comment = await cto_approval(
                f"Проект '{project['title']}'", project["title"],
                "Дизайн-решение выработано командой по итогам обсуждения фаз DIGEST/DESIGN.",
                design_summary,
            )
            verdict = f"{'✅ ОДОБРЕНО' if approved else '❌ ОТКЛОНЕНО — возврат в DESIGN'}: {comment}"
            send_telegram_report(f"🧭 Согласование проекта «{project['title']}»: {verdict}")
            if approved:
                project["phase"] = "IMPLEMENTATION"
            else:
                project["phase"] = "DESIGN"
            save_project(project)

        elif project["phase"] == "DONE":
            send_telegram_report(f"🎉 Проект «{project['title']}» полностью завершён!")

    if project["phase"] == "IMPLEMENTATION":
        print(f"[{project_id}] Фаза реализации — запускаем инженерные задачи по частям...")
        from workflows.engineering_task import run_engineering_task

        design_summary = "\n".join(d["summary"] for d in project["decisions"])
        client = get_chat_client(BOARD_MODEL_ASSIGNMENTS.get("agenda_setter", "gpt-5.2"))
        parts_prompt = f"""
Проект: {project['title']}
Согласованный дизайн: {design_summary}

Разбей реализацию на 1-3 конкретные технические задачи (каждая —
одно предложение, реализуемое отдельно). Может быть и backend
(bld-system), и панель (bld-panel) — не ограничивайся одним
репозиторием. Ответь списком, каждая задача с новой строки, без
нумерации и лишнего текста.
"""
        parts_response = await ask(client, parts_prompt)
        parts = [p.strip("- ").strip() for p in parts_response.split("\n") if p.strip() and len(p.strip()) > 10]

        for part in parts[:3]:
            if is_duplicate(part):
                continue
            task_id = add_task(part, f"project:{project_id}", status="in_progress", reason=design_summary[:200])
            try:
                report = await run_engineering_task(part)
            except Exception as e:
                print(f"[{project_id}] run_engineering_task упал с исключением на части '{part}': {e}")
                update_task_status(task_id, "rejected", f"Упало с необработанным исключением: {e}")
                send_telegram_report(f"❌ Часть проекта «{project['title']}» упала с ошибкой: {part}\n\nОшибка: {e}")
                continue
            update_task_status(task_id, "done")
            send_telegram_report(f"👷 РЕАЛИЗОВАНО (проект «{project['title']}»)\n\n{report}")
            await curate_knowledge(f"Проект {project_id}: реализовано", report)

        project["phase"] = "DONE"
        save_project(project)
        send_telegram_report(f"🎉 Проект «{project['title']}» полностью реализован!")


async def generate_facets_from_brief(title: str, brief: str) -> list[list]:
    """Через LLM разбивает бриф на 2-4 грани обсуждения (facet_key,
    facet_desc, facet_keywords) — тот же формат, что вручную заданные
    facets в PROJECTS_REGISTRY выше (seasonal_mode — пример разметки
    руками). Нужна для register_project() ниже, когда facets не
    переданы явно: формулировать их руками для каждой новой
    само-зарегистрированной идеи было бы снова той самой правкой кода,
    от которой Дыра №2 (см. ТЗ) уходит."""
    from config.client_factory import get_chat_client

    client = get_chat_client(BOARD_MODEL_ASSIGNMENTS.get("agenda_setter", "gpt-5.2"))
    prompt = f"""
Проект: {title}

Бриф:
{brief}

Разбей реализацию этого проекта на 2-4 конкретные грани обсуждения —
как их обсуждали бы параллельные небольшие группы специалистов, каждая
грань — отдельный угол именно ЭТОГО брифа (например: UX, данные/бэкенд,
бизнес-обоснование, инфраструктура — конкретно под задачу, не общий
шаблон "UX/данные/бизнес" бездумно).

Для каждой грани ответь ТРЕМЯ строками подряд без нумерации, блоки
разделяй пустой строкой:
КЛЮЧ: [короткий английский идентификатор, snake_case, без пробелов]
ОПИСАНИЕ: [1 предложение — что именно обсуждает эта группа]
КЛЮЧЕВЫЕ_СЛОВА: [3-6 слов/словосочетаний через запятую, по-русски — для подбора релевантных специалистов]
"""
    response = await ask(client, prompt)

    facets: list[list] = []
    key = desc = None
    for line in response.split("\n"):
        line = line.strip()
        if line.upper().startswith("КЛЮЧ:"):
            key = line.split(":", 1)[-1].strip().lower().replace(" ", "_") or f"facet_{len(facets) + 1}"
        elif line.upper().startswith("ОПИСАНИЕ:"):
            desc = line.split(":", 1)[-1].strip()
        elif line.upper().startswith("КЛЮЧЕВЫЕ_СЛОВА:") or line.upper().startswith("КЛЮЧЕВЫЕ СЛОВА:"):
            kws = [k.strip().lower() for k in line.split(":", 1)[-1].strip().split(",") if k.strip()]
            if key and desc:
                facets.append([key, desc, kws])
            key = desc = None

    if not facets:
        # Честный фолбэк — одна общая грань, лучше, чем упасть с
        # пустым списком (run_project_day с facets=[] технически не
        # упадёт на asyncio.gather(*[]), но проект тогда никогда не
        # продвинется ни на шаг — DIGEST так и останется пустым вечно).
        facets = [["general", "Общее осмысление и реализация проекта целиком", []]]
    return facets[:4]


async def register_project(project_id: str, title: str, brief: str,
                            facets: list[list] | None = None) -> dict:
    """Регистрирует НОВЫЙ крупный проект в .state/projects/{project_id}.json
    — БЕЗ правки PROJECTS_REGISTRY в коде. Это и есть закрытие Дыры №2
    (см. ТЗ): раньше единственный способ завести проект — вручную
    дописать словарь в этом файле и закоммитить, то есть даже если идея
    родилась и была одобрена в обсуждении (совет директоров,
    Company Pulse), она терялась, пока Валик сам не вспоминал и не
    правил код. Теперь любой воркфлоу (board_meeting.py, goal_intake.py)
    может вызвать это напрямую.

    Если facets не переданы явно — генерируются автоматически
    (generate_facets_from_brief). Если project_id уже существует на
    диске — возвращает существующий ПРОЕКТ БЕЗ ИЗМЕНЕНИЙ (идемпотентно;
    не даёт повторной регистрацией случайно затереть прогресс уже
    идущего проекта).

    ВАЖНО: регистрация НЕ обходит согласование — новый проект стартует
    с phase="DIGEST", реализация (IMPLEMENTATION) по-прежнему наступит
    только после APPROVAL-фазы (см. run_project_day() ниже, cto_approval()
    там как был, так и остался обязательным шагом). Само-регистрация
    ускоряет только "завести проект", не "согласовать и запустить в
    работу без спроса".
    """
    existing_path = project_path(project_id)
    if existing_path.exists():
        print(f"[big_projects] Проект '{project_id}' уже существует — регистрация пропущена, возвращаю как есть.")
        return load_project(project_id)

    if facets is None:
        facets = await generate_facets_from_brief(title, brief)

    project = {
        "id": project_id,
        "title": title,
        "brief": brief,
        "facets": facets,
        "phase": "DIGEST",
        "log": [],
        "decisions": [],
        "created": datetime.now().isoformat(),
    }
    save_project(project)
    print(f"[big_projects] Новый проект зарегистрирован: '{project_id}' ({title}), {len(facets)} граней.")
    return project


def list_active_project_ids() -> list[str]:
    """Все project_id с phase != DONE — легаси из PROJECTS_REGISTRY
    (проекты, для которых ещё нет файла на диске, считаются активными
    по умолчанию — они ещё не начинались, фаза DIGEST) И
    само-зарегистрированные из .state/projects/*.json, включая те,
    каких вообще нет в PROJECTS_REGISTRY (именно то, что даёт
    register_project()). Используется main() ниже, когда project_id не
    передан явно — раньше в этом случае ВСЕГДА бралась только
    'seasonal_mode' (см. main() ниже и .github/workflows/big_project_day.yml
    — там был жёсткий дефолт), то есть новые само-зарегистрированные
    проекты никогда бы не попали на cron-расписание, даже если бы
    register_project() уже существовала."""
    ids = set(PROJECTS_REGISTRY.keys())
    if PROJECTS_DIR.exists():
        ids.update(p.stem for p in PROJECTS_DIR.glob("*.json"))

    active = []
    for pid in sorted(ids):
        try:
            project = load_project(pid)
        except KeyError:
            continue
        if project.get("phase") != "DONE":
            active.append(pid)
    return active


async def main():
    import sys
    if len(sys.argv) > 1:
        await run_project_day(sys.argv[1])
        return

    # РАНЬШЕ: без явного аргумента ВСЕГДА бралась 'seasonal_mode' —
    # единственный проект, существовавший на момент написания этого
    # файла. Cron-расписание (.github/workflows/big_project_day.yml)
    # не передаёт аргумент вообще, так что каждый пятничный тик молча
    # прогонял только сезонный режим, даже если появлялись другие
    # активные проекты. ТЕПЕРЬ без аргумента — работаем параллельно
    # (как squad_initiative.py делает для отрядов) над ВСЕМИ активными
    # проектами сразу, включая само-зарегистрированные через
    # register_project().
    active = list_active_project_ids()
    if not active:
        print("Нет активных проектов ('20% времени') — нечего делать в этот тик.")
        return
    print(f"Активных проектов: {len(active)} ({', '.join(active)}) — работаем над всеми параллельно.")
    await asyncio.gather(*(run_project_day(pid) for pid in active))


if __name__ == "__main__":
    asyncio.run(main())
