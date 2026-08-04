"""
Инженерная команда — в отличие от совета директоров и код-ревью
команды, эти агенты РЕАЛЬНО пишут и коммитят код в bld-system/bld-panel
(в отдельную ветку, никогда не в main — см. tools/repo_tools.py:
write_file/commit_and_push отказывают на защищённых ветках). Мерж в
main — автоматический через Review Gate при чистом вердикте
(merge_branch_to_main в tools/repo_tools.py, вызывается из
workflows/engineering_task.py и workflows/squad_task.py), без участия
основателя; при проблемах решение — за CTO.

Ведущий инженер — максимально "нагруженная" техническая подготовка:
физтех + физмат + техмат + мехмат разом, будто отучился во всех школах
одновременно. Ему можно доверить любую задачу. Он САМ решает, справится
один или нужно привлечь ещё инженеров — без фиксированных "3-5 дней",
объём определяется по факту сложности того, что видно в реальном коде.
Привлечённые инженеры (junior) обычно на моделях подешевле — не всем
задачам нужен топ.
"""

from agents._shared_context import RIGOR_MANDATE
from config.client_factory import get_chat_client
from tools.repo_tools import git_diff, git_log, grep_repo, list_repo_files, read_file, write_file

ENGINEERING_TOOLS = [list_repo_files, read_file, git_log, git_diff, grep_repo, write_file]

LEAD_INSTRUCTIONS = f"""
Ты — ведущий инженер компании. Твоя подготовка объединяет физтех (стык
hardware/software, системное мышление, инженерное чутьё), физмат
(статистика, эксперимент, научный метод), техмат (прикладная инженерия,
надёжность, реальные ограничения) и мехмат (чистые алгоритмы,
доказательная строгость) — всё разом, будто прошёл все эти школы. Тебе
можно доверить любую техническую задачу — от точечной правки функции
до архитектурного рефакторинга.

У тебя 20 лет практического опыта: 8 лет в Google (инфраструктурные
системы), затем 7 лет в Amazon (распределённые backend-системы), и
несколько последних лет как staff-инженер, консультирующий стартапы
по архитектуре. Ты не теоретик — ты писал код, который держал реальную
нагрузку, и разгребал последствия кода, который её не держал. Именно
поэтому тебе доверяют реальный write-доступ к коду — остальные в
компании (совет директоров, код-ревью команда) сознательно ограничены
только чтением, а ты и привлекаемые тобой специалисты — нет.

Тебе поставлена задача по проекту BLD System (мониторинг стройплощадок,
Telegram-бот + AI-парсинг + anomaly detection engine + React-панель).
У тебя есть tools для РЕАЛЬНОЙ работы с кодом: list_repo_files,
read_file, git_log, git_diff, grep_repo, write_file.

Твой процесс:
0. ПРЕЖДЕ ВСЕГО проверь: это вообще осмысленная техническая задача про
   BLD System? Если текст задачи выглядит как жалоба другой модели на
   нехватку данных ("пришлите стенограмму", "у меня нет текста", "нет
   данных для отчёта" и подобное) — это НЕ задача, это испорченный
   мусор, долетевший до тебя по ошибке из другого этапа пайплайна.
   В этом случае НЕ пиши никакой код, а просто ответь одним абзацем:
   "ЗАДАЧА НЕ ОСМЫСЛЕННА: <объяснение>" — и остановись. Не пытайся
   притянуть эту фразу к реальной фиче в продукте (например, не
   добавляй в бота обработку сообщений про 'стенограмму' — это не
   имеет отношения к мониторингу стройплощадок).
1. Разберись в задаче и реальном коде — прочитай нужные файлы, посмотри
   историю, поищи связанные места через grep_repo.
2. Реши сам: справишься в одиночку, или задача достаточно большая/
   многосоставная, чтобы разбить её на явные части и привлечь ещё
   инженеров. Не привязывайся к шаблонным срокам вроде "3-5 дней" —
   объём и число нужных людей определяй по факту того, что видишь в
   коде, а не по абстрактной оценке.
3. Если справляешься один — напиши РЕАЛЬНЫЙ рабочий код через
   write_file для каждого изменяемого/нового файла. Не пиши
   плейсхолдеры или "TODO: implement" — доводи реализацию до конца,
   с учётом существующих в проекте конвенций (импорты, стиль структура
   модулей, как называются похожие функции рядом).
4. Если решаешь привлечь ещё инженеров — явно опиши (текстом, в конце
   ответа), на какие части разбивается оставшаяся работа и что именно
   должен сделать каждый привлечённый инженер. Это описание станет их
   техническим заданием.

Обязательно заверши текстовым резюме: что сделано, какие файлы
затронуты, что нужно проверить/протестировать перед мерджем в main,
и (если применимо) что осталось для привлечённых инженеров.
{RIGOR_MANDATE}
"""


def build_lead_engineer(model_name: str):
    return get_chat_client(model_name).as_agent(
        name="lead_engineer",
        instructions=LEAD_INSTRUCTIONS,
        tools=ENGINEERING_TOOLS,
    )


def build_junior_engineer(model_name: str, index: int):
    return get_chat_client(model_name).as_agent(
        name=f"engineer_{index}",
        instructions="""
Тебя привлёк ведущий инженер для конкретной части более крупной задачи.
Тебе дадут техническое задание (часть общей задачи) и контекст всей
задачи целиком.

У тебя есть tools для реальной работы с кодом: list_repo_files,
read_file, git_log, git_diff, grep_repo, write_file. Разберись в коде,
напиши РЕАЛЬНУЮ рабочую реализацию именно своей части (через
write_file) — не плейсхолдер, а готовый код с учётом конвенций проекта.
Не трогай то, что явно не относится к твоей части задачи.

В конце — короткое текстовое резюме: что именно сделал, какие файлы
затронул.
""",
        tools=ENGINEERING_TOOLS,
    )


def build_specialist_pool() -> dict:
    """Пул именных специалистов (архетипы мировых топ-вузов + инженерный
    спецназ + Global Elite I/II/III/IV/V/VI), которых лид-инженер может
    'нанять' под конкретную задачу — все с write_file, реально пишут
    код. Используется вместо generic junior_engineer, когда нужен
    конкретный профиль (надёжность → ETH или Reliability Engineer,
    скорость вычислений → USTC, latency прода → Performance Engineer,
    и т.д. — см. SPECIALTY_KEYWORDS в agents/global_geniuses.py,
    agents/specialists.py и agents/global_elite.py /
    agents/global_elite_100.py / agents/global_elite_3.py /
    agents/global_elite_4.py / agents/global_elite_5.py /
    agents/global_elite_6.py)."""
    from agents.architecture_council import ARCHITECT_BUILDERS
    from agents.engineering_fellows import FELLOW_BUILDERS
    from agents.expansion_geniuses import GENIUS_BUILDERS as EXPANSION_BUILDERS
    from agents.global_elite import ELITE1_BUILDERS
    from agents.global_elite_100 import ELITE2_BUILDERS
    from agents.global_elite_3 import ELITE3_BUILDERS
    from agents.global_elite_4 import ELITE4_BUILDERS
    from agents.global_elite_5 import ELITE5_BUILDERS
    from agents.global_elite_6 import ELITE6_BUILDERS
    from agents.global_geniuses import GENIUS_BUILDERS
    from agents.growth_team import GROWTH_BUILDERS
    from agents.specialists import SPECIALIST_BUILDERS

    pool = {name: builder(can_write=True) for name, builder in GENIUS_BUILDERS.items()}
    pool.update({name: builder(can_write=True) for name, builder in SPECIALIST_BUILDERS.items()})
    pool.update({name: builder(can_write=True) for name, builder in GROWTH_BUILDERS.items()})
    pool.update({name: builder(can_write=True) for name, builder in EXPANSION_BUILDERS.items()})
    pool.update({name: builder(can_write=True) for name, builder in ARCHITECT_BUILDERS.items()})
    pool.update({name: builder(can_write=True) for name, builder in FELLOW_BUILDERS.items()})
    pool.update({name: builder(can_write=True) for name, builder in ELITE1_BUILDERS.items()})
    pool.update({name: builder(can_write=True) for name, builder in ELITE2_BUILDERS.items()})
    pool.update({name: builder(can_write=True) for name, builder in ELITE3_BUILDERS.items()})
    pool.update({name: builder(can_write=True) for name, builder in ELITE4_BUILDERS.items()})
    pool.update({name: builder(can_write=True) for name, builder in ELITE5_BUILDERS.items()})
    pool.update({name: builder(can_write=True) for name, builder in ELITE6_BUILDERS.items()})
    return pool


def pick_specialist(lead_summary: str, pool: dict) -> tuple[str, object]:
    """По ключевым словам в тексте лида определяет наиболее подходящего
    специалиста из пула (включая 550 человек Global Elite I/II/III/IV/V/VI);
    если явных совпадений нет — берёт случайного.

    ВАЖНО (исправлено при добавлении Global Elite IV, актуально и для
    V): раньше это была линейная функция "первое совпадение побеждает"
    по порядку слияния словарей — значит, чем позже волна добавлена в
    all_keywords, тем реже её ключи реально сравнивались (их забивал
    более общий keyword из более раннего словаря). Теперь сравниваются
    ВСЕ совпадения по всем специалистам, и побеждает самое специфичное
    (самое длинное) совпавшее ключевое слово — не важно, из какого
    словаря и в каком порядке он импортирован.

    ДОБАВЛЕНО при расширении департаментов (agents/squads.py, 7 вместо
    4, пулы по 20-80 человек): при РАВНОЙ специфичности раньше побеждал
    тот, кто первым попался в порядке итерации словаря — то есть
    систематически один и тот же человек при большом пуле с несколькими
    одинаково подходящими кандидатами. Теперь при ничьей — честная
    ротация через fair_sample() (тот же общий трекер участия
    .state/participation.json, что и у Pulse/Chevruta/Lab/HR)."""
    import random

    from agents.architecture_council import SPECIALTY_KEYWORDS as ARCHITECT_KEYWORDS
    from agents.engineering_fellows import SPECIALTY_KEYWORDS as FELLOW_KEYWORDS
    from agents.expansion_geniuses import SPECIALTY_KEYWORDS as EXPANSION_KEYWORDS
    from agents.global_elite import ELITE1_SPECIALTY_KEYWORDS
    from agents.global_elite_100 import ELITE2_SPECIALTY_KEYWORDS
    from agents.global_elite_3 import ELITE3_SPECIALTY_KEYWORDS
    from agents.global_elite_4 import ELITE4_SPECIALTY_KEYWORDS
    from agents.global_elite_5 import ELITE5_SPECIALTY_KEYWORDS
    from agents.global_elite_6 import ELITE6_SPECIALTY_KEYWORDS
    from agents.global_geniuses import SPECIALTY_KEYWORDS as GENIUS_KEYWORDS
    from agents.growth_team import SPECIALTY_KEYWORDS as GROWTH_KEYWORDS
    from agents.specialists import SPECIALTY_KEYWORDS as SPECIALIST_KEYWORDS
    from workflows._common import fair_sample

    all_keywords = {
        **GENIUS_KEYWORDS, **SPECIALIST_KEYWORDS, **GROWTH_KEYWORDS, **EXPANSION_KEYWORDS,
        **ARCHITECT_KEYWORDS, **FELLOW_KEYWORDS, **ELITE1_SPECIALTY_KEYWORDS, **ELITE2_SPECIALTY_KEYWORDS,
        **ELITE3_SPECIALTY_KEYWORDS, **ELITE4_SPECIALTY_KEYWORDS, **ELITE5_SPECIALTY_KEYWORDS,
        **ELITE6_SPECIALTY_KEYWORDS,
    }
    lowered = lead_summary.lower()
    best_score = 0
    best_names: list[str] = []
    for name, keywords in all_keywords.items():
        if name not in pool:
            continue
        for kw in keywords:
            if kw not in lowered:
                continue
            if len(kw) > best_score:
                best_score, best_names = len(kw), [name]
            elif len(kw) == best_score and name not in best_names:
                best_names.append(name)
    if best_names:
        name = fair_sample(best_names, k=1)[0]
        return name, pool[name]
    name = random.choice(list(pool.keys()))
    return name, pool[name]
