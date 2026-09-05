"""
/goal — единая точка входа: Валик формулирует цель свободным текстом,
дальше система сама решает, как её раскладывать по существующим
механизмам компании, не требуя писать промпт на каждый шаг вручную.

РАНЬШЕ такой точки не было вообще — все механизмы (squad_initiative,
big_projects, gtm_initiative, board_meeting) запускались независимо по
расписанию или явным CLI-аргументом; tools/telegram_report.py умеет
ТОЛЬКО отправлять сообщения, входящих команд не принимает (проверено:
нигде в репозитории нет кода, который бы читал Telegram getUpdates).

ЭТОТ МОДУЛЬ НЕ ЗАПУСКАЕТ ОТДЕЛЬНЫЙ ПАРАЛЛЕЛЬНЫЙ ДВИЖОК — это тонкий
диспетчерский слой поверх уже работающих циклов:
1. Классифицирует цель (triage_goal) — bugfix/feature/cross_department/
   new_system/gtm. Для new_system дополнительно решает: это доработка
   внутри существующего BLD, или отдельный самостоятельный продукт
   цифровизации стройки (свой репозиторий) — Валик как CDTO может
   ставить цели не только про BLD (см. context/company_context.md).
2. Заводит подзадачу(и) на общей доске (workflows/task_board.py) с
   общим goal_id — так позже видно, что относится к этой цели, даже
   если она разъехалась по нескольким департаментам.
3. Передаёт выполнение УЖЕ СУЩЕСТВУЮЩЕМУ механизму (run_squad_task,
   run_squad_relay, big_projects.register_project, gtm_initiative) —
   никакой новой логики выполнения здесь нет, только маршрутизация.
4. Статус цели по goal_id — отдельный модуль, workflows/goal_status.py
   (суточный обзор всех незавершённых целей + запрос по конкретному
   goal_id).

РЕАЛИСТИЧНЫЙ КАНАЛ ВВОДА: у bld-team нет живого сервера, принимающего
вебхуки (вся компания живёт на GitHub Actions cron + workflow_dispatch)
— поэтому /goal в буквальном смысле "команда в Telegram" здесь НЕ
реализована (это отдельная небольшая инфраструктурная задача — принять
вебхук от Telegram и превратить его в repository_dispatch, можно
сделать отдельно). Реальный интерфейс сейчас — GitHub Actions
workflow_dispatch с текстовым полем (.github/workflows/goal.yml) или
CLI: python main_goal.py "текст цели". Технически это уже "написал
цель — оно пошло работать", просто кнопка не в Telegram, а в GitHub
Actions (или `gh workflow run goal.yml -f goal="..."` с телефона через
GitHub-приложение).
"""

import asyncio
import re
import uuid

from config.client_factory import get_chat_client
from config.models import BOARD_MODEL_ASSIGNMENTS
from workflows._common import ask, notify_done, notify_failed
from workflows.board_meeting import assign_task_to_squad
from workflows.squad_task import detect_relevant_squads, run_squad_relay, run_squad_task
from workflows.task_board import add_task, is_duplicate, update_task_status

GOAL_TYPES = ("bugfix", "feature", "cross_department", "new_system", "gtm")


def make_goal_id(goal_text: str) -> str:
    """slug оставляем строго ASCII — goal_id для типа new_system
    напрямую становится именем файла проекта (project_path() в
    workflows/big_projects.py, .state/projects/{project_id}.json), а
    Валик обычно формулирует цели по-русски/украински — кириллица в
    slug технически не ломает большинство файловых систем, но
    создаёт ненужный риск (git/CI на разных ОС, кавычки в путях) там,
    где легко обойтись без него. Кириллица просто выбрасывается, не
    транслитерируется — транслитерация читаемее, но это лишняя
    сложность ради идентификатора, который всё равно не для чтения
    человеком (человеку читаемое название — отдельное поле title,
    возвращаемое triage_goal, goal_id только для внутренних ссылок)."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", goal_text.lower()).strip("-")[:40]
    if not slug:
        slug = "goal"
    return f"goal-{slug}-{uuid.uuid4().hex[:6]}"


async def triage_goal(goal_text: str) -> dict:
    """Классифицирует свободный текст цели — решает, каким из
    существующих механизмов её обрабатывать. Не изобретает новый
    способ выполнения: результат триажа — это только маршрут к уже
    работающим циклам (run_squad_task/run_squad_relay/register_project/
    run_gtm_initiative)."""
    client = get_chat_client(BOARD_MODEL_ASSIGNMENTS.get("agenda_setter", "gpt-5.2"))
    prompt = f"""
Цель от Валика (CDTO — цифровизация стройки; BLD System — основной,
но не единственный продукт в портфеле): {goal_text}

Классифицируй эту цель РОВНО в одну из категорий:

bugfix — конкретная мелкая правка/баг в известной зоне, один
    департамент, не требует долгого обсуждения.
feature — фича/улучшение в рамках ОДНОГО департамента — не мелочь, но
    и не то, что требует многодневного проектирования с нуля.
cross_department — задача явно затрагивает НЕСКОЛЬКО департаментов
    одновременно (например, и данные/бэкенд, и интерфейс, и т.п.).
new_system — построить что-то принципиально новое "с нуля", требует
    многодневного осмысления/дизайна/согласования разными гранями
    (данные + UX + бизнес-обоснование и т.п.) — НЕ однодневная задача.
gtm — про продажи, ценообразование, привлечение клиентов, маркетинг —
    не техническая задача вообще.

Если ТИП = new_system, реши ДОПОЛНИТЕЛЬНО: это доработка/подсистема
внутри существующего BLD (использует его данные/пользователей/бота) —
тогда РЕПО оставь пустым; или это ОТДЕЛЬНЫЙ, самостоятельный продукт
цифровизации стройки (свой интерфейс, свой бэкенд, не довесок к BLD,
даже если тоже про стройку) — тогда предложи короткий английский
snake_case слаг под новый репозиторий (например "smeta-tracker",
"tender-radar") в РЕПО. Для всех остальных типов РЕПО всегда пустое.

Ответь строго в формате:
ТИП: [bugfix|feature|cross_department|new_system|gtm]
НАЗВАНИЕ: [одна строка — конкретная формулировка задачи/проекта]
ОБОСНОВАНИЕ: [1-2 предложения — почему именно эта категория]
РЕПО: [snake_case слаг нового репозитория, ТОЛЬКО если это отдельный
    продукт вне BLD; иначе оставь строку пустой после двоеточия]
"""
    response = await ask(client, prompt)

    goal_type = "feature"
    title = goal_text.strip()
    reason = ""
    repo = ""
    for line in response.split("\n"):
        if line.upper().startswith("ТИП:"):
            raw = line.split(":", 1)[-1].strip().lower()
            for t in GOAL_TYPES:
                if t.replace("_", "") in raw.replace("_", "").replace(" ", ""):
                    goal_type = t
                    break
        elif line.upper().startswith("НАЗВАНИЕ:"):
            title = line.split(":", 1)[-1].strip() or title
        elif line.upper().startswith("ОБОСНОВАНИЕ:"):
            reason = line.split(":", 1)[-1].strip()
        elif line.upper().startswith("РЕПО:"):
            raw_repo = line.split(":", 1)[-1].strip()
            repo = re.sub(r"[^a-z0-9\-]+", "-", raw_repo.lower()).strip("-")

    return {"type": goal_type, "title": title, "reason": reason, "repo": repo or None}


async def dispatch_goal(goal_text: str) -> str:
    """Полный цикл /goal: классифицирует, заводит подзадачу(и) на
    доске с общим goal_id, запускает подходящий существующий механизм.
    Возвращает goal_id — им потом смотреть статус (workflows/goal_status.py).
    """
    goal_id = make_goal_id(goal_text)
    triage = await triage_goal(goal_text)
    goal_type, title, reason = triage["type"], triage["title"], triage["reason"]

    print(f"[goal:{goal_id}] Тип: {goal_type}. Название: {title}. Обоснование: {reason}")

    if goal_type == "gtm":
        # GTM — отдельная область (workflows/gtm_initiative.py), не
        # инженерная работа. run_gtm_initiative сама заводит задачу на
        # доске и шлёт отчёт — здесь только передаём ей текст цели и
        # goal_id, ничего не дублируем.
        from workflows.gtm_initiative import run_gtm_initiative
        await run_gtm_initiative(task_hint=goal_text, goal_id=goal_id)
        # run_gtm_initiative уже сама шлёт notify_done()/notify_failed() —
        # не дублируем отдельной строкой "обработан через GTM".
        return goal_id

    if goal_type == "new_system":
        # register_project() (workflows/big_projects.py) НЕ реализует
        # проект синхронно здесь же — только регистрирует бриф и грани
        # (phase=DIGEST). Дальше проект пойдёт своим обычным циклом
        # через main_big_project_day.py / расписание Big Project Day —
        # APPROVAL остаётся обязательным шагом, /goal его не обходит.
        from workflows.big_projects import register_project

        project_id = goal_id.replace("goal-", "project-")
        repo = triage.get("repo")  # None = доработка внутри BLD; иначе — отдельный продукт, свой репозиторий
        task_id = add_task(title, f"project:{project_id}", status="proposed",
                            reason=reason, goal_id=goal_id, repo=repo)
        project = await register_project(project_id, title, goal_text, repo=repo)
        repo_note = f", отдельный продукт (репозиторий: {repo})" if repo else " (в рамках существующего BLD)"
        update_task_status(
            task_id, "in_progress",
            f"Зарегистрирован как крупный проект '{project_id}'{repo_note} — пойдёт через "
            f"DIGEST → DESIGN → APPROVAL → IMPLEMENTATION.",
        )
        print(f"🎯 /goal → зарегистрирован как крупный проект «{project['title']}» (id: {project_id}){repo_note}, goal_id: {goal_id}")
        # РАНЬШЕ длинное объяснение цикла уходило в Telegram — убрано:
        # это старт, не готовая работа. Итоговое завершение проекта
        # уведомит само (workflows/big_projects.py::notify_done).
        return goal_id

    if goal_type == "cross_department":
        relevant = detect_relevant_squads(title) or detect_relevant_squads(goal_text)
        if len(relevant) >= 2:
            if is_duplicate(title):
                notify_done(f"/goal: похожая задача уже на доске, не дублирую (goal_id: {goal_id})")
                return goal_id
            zones = "+".join(relevant)
            task_id = add_task(title, f"relay:{zones}", status="in_progress",
                                reason=reason, goal_id=goal_id)
            try:
                relay_report = await run_squad_relay(title, order=relevant, task_id=task_id)
                update_task_status(task_id, "done")
                print(relay_report)
                notify_done(f"/goal → эстафета {zones} (goal_id: {goal_id})")
            except Exception as e:
                update_task_status(task_id, "rejected", f"Упало с необработанным исключением: {e}")
                print(f"❌ /goal (эстафета {zones}) упала с ошибкой: {e}")
                notify_failed(f"/goal → эстафета {zones} (goal_id: {goal_id})", str(e))
            return goal_id

        # Триаж сказал cross_department, но detect_relevant_squads по
        # ключевым словам нашёл меньше 2 зон (формулировка цели не
        # совпала с domain_keywords дословно) — не падаем, честно
        # откатываемся на обычный путь одного департамента ниже, а не
        # молча теряем цель.
        print(f"[goal:{goal_id}] Триаж сказал cross_department, но detect_relevant_squads нашёл только {relevant} — обрабатываю как обычную задачу.")

    # bugfix / feature (и откат из cross_department выше) — обычная
    # задача одного департамента, тот же путь, что squad_initiative.py
    # использует для самостоятельно найденных задач, только запущенный
    # по цели от Валика, а не по инициативе отряда.
    target_squad = assign_task_to_squad(title)
    if is_duplicate(title):
        notify_done(f"/goal: похожая задача уже на доске, не дублирую (goal_id: {goal_id})")
        return goal_id

    task_id = add_task(title, target_squad, status="in_progress", reason=reason, goal_id=goal_id)
    try:
        report = await run_squad_task(target_squad, title, task_id=task_id)
        update_task_status(task_id, "done")
        print(report)
        notify_done(f"/goal → {target_squad} (goal_id: {goal_id})")
    except Exception as e:
        update_task_status(task_id, "rejected", f"Упало с необработанным исключением: {e}")
        print(f"❌ /goal упала с ошибкой: {e}")
        notify_failed(f"/goal → {target_squad} (goal_id: {goal_id})", str(e))
    return goal_id


async def main():
    import sys
    goal_text = " ".join(sys.argv[1:]).strip()
    if not goal_text:
        print('Использование: python main_goal.py "текст цели"')
        return
    goal_id = await dispatch_goal(goal_text)
    print(f"goal_id: {goal_id}")


if __name__ == "__main__":
    asyncio.run(main())
