"""
Review Gate — проверка результата инженерной задачи ПЕРЕД тем как
отчёт уйдёт Валику. Это то, чего не хватало: раньше отчёт "инженерная
задача выполнена" уходил сразу после коммита, без единой проверки.
Теперь между "код написан" и "отчёт отправлен" стоит настоящий gate —
как в реальных компаниях.

ЧЕТЫРЕ роли, четыре разных угла:
- Chief Architect — архитектурное вето. "Его 'нет' не обсуждается":
  не управляет людьми, владеет границами архитектуры и техническим
  долгом. Смотрит НЕ на "работает ли", а на "не создаёт ли это
  проблему через полгода".
- Reviewer — объединяет Principal Reviewer (approve/reject по
  качеству кода) и Complexity Auditor (алгоритмическая строгость,
  Big O, лишняя сложность) в одну практичную роль код-ревьюера.
- Failure Engineer — Chaos Engineering по духу: специально пытается
  СЛОВАМИ придумать, как сломать то, что только что написали.
- Fuzzer — НЕ просто ещё одно мнение. Пишет реальные edge-case тесты
  (write_file) и они РЕАЛЬНО прогоняются через pytest
  (tools.repo_tools.run_test_suite). Специально на модели не из той
  же линейки, что пишет код (не GPT) — разные модели ловят разные
  слепые пятна. Сильные модели на ревью важны, но это не замена
  классике (CI/тесты/fuzzing), а дополнение поверх нее — реальный
  результат теста не обсуждается, в отличие от текстового мнения.

ВАЖНО: architect/reviewer/failure_engineer только ЧИТАЮТ (git_diff,
read_file и т.д.), НЕ пишут код — их роль оценивать, а не переписывать
за инженеров. Fuzzer — единственное осознанное исключение: ему можно
писать, но ТОЛЬКО тестовые файлы, не продакшен-код (см. его инструкции).
"""

from config.client_factory import get_chat_client
from config.models import REVIEW_GATE_MODEL_ASSIGNMENTS
from tools.repo_tools import commit_and_push, git_diff, git_log, grep_repo, list_repo_files, read_file, run_test_suite, write_file

REVIEW_TOOLS = [list_repo_files, read_file, git_log, git_diff, grep_repo]
FUZZ_TOOLS = [list_repo_files, read_file, git_log, git_diff, grep_repo, write_file]

from agents._shared_context import RIGOR_MANDATE, load_bld_scope_context
from workflows._common import safe_agent_run

COMPANY_CONTEXT = load_bld_scope_context()

EXPERIENCE = {
    "chief_architect": (
        "20 лет архитектуры распределённых систем — участвовал в "
        "развитии внутренней инфраструктуры Google (в духе Borg/Omega) "
        "и позже архитектурой платформы в Amazon. Твоё 'нет' стоит "
        "того, чтобы к нему прислушались — оно основано на десятках "
        "систем, которые ты видел живыми и умершими."
    ),
    "reviewer": (
        "18 лет практики код-ревью в Google — счёт пошёл на тысячи "
        "ревью, включая те, что предотвратили серьёзные инциденты. "
        "Плюс background в спортивном программировании (Codeforces "
        "2400+) — сложность алгоритмов ты чувствуешь кожей."
    ),
    "failure_engineer": (
        "12 лет Chaos Engineering в Netflix — буквально зарабатывал на "
        "жизнь тем, что специально ломал прод, чтобы найти слабые места "
        "до того, как их найдёт реальный инцидент в пятницу вечером."
    ),
    "fuzzer": (
        "10 лет security research и fuzz testing — находил 0-day уязвимости "
        "через автоматизированную генерацию нестандартных входных данных "
        "(American Fuzzy Lop, libFuzzer, property-based testing в духе "
        "Hypothesis). Ты не предполагаешь, ломается код или нет — ты "
        "пишешь тест, который это ПРОВЕРЯЕТ, и смотришь на реальный "
        "результат."
    ),
}

FUZZ_TASK_TEMPLATE = """
Инженерная команда только что написала код по задаче и запушила его
в ветку "{branch_name}" репозитория "{repo_name}" (НЕ в main).

Исходная задача: {task}

Резюме от инженеров о том, что сделано:
{engineering_summary}

Посмотри реальный diff (git_diff) и затронутые файлы (read_file).
Структура тестов в этом репозитории: tests/unit, tests/integration,
tests/regression, tests/smoke (pytest + pytest-asyncio) — посмотри
list_repo_files/grep_repo по tests/, чтобы понять конвенции именования
и стиль существующих тестов в этом проекте, ПРЕЖДЕ чем писать свои.

Придумай 2-4 РЕАЛИСТИЧНЫХ edge-case/adversarial сценария конкретно под
это изменение (не общие банальности) — необычные/граничные входные
данные, пустые/None значения там, где их не ждут, конкурентный доступ,
превышение лимитов, повреждённые данные. Затем НАПИШИ настоящие
исполняемые pytest-тесты для этих сценариев через write_file — в
подходящую директорию (обычно tests/unit или tests/regression, смотря
что тестируешь), следуя стилю существующих тестов проекта.

ВАЖНО — жёсткая граница: пиши ТОЛЬКО тестовый код (test_*.py). НЕ
трогай продакшен-код — если видишь баг, который твой тест обнажит,
опиши его словами в ответе, чтобы это увидели остальные ревьюеры и
инженеры, а не чини его сам. Твоя работа — проверять, не переписывать.

В конце ответа коротко перечисли, какие файлы создал/дополнил и что
именно каждый тест проверяет — реальный результат их выполнения ты
увидишь отдельно после того, как они прогонятся по-настоящему.
"""

REVIEW_TASK_TEMPLATE = """
Инженерная команда только что написала код по задаче и запушила его
в ветку "{branch_name}" репозитория "{repo_name}" (НЕ в main).

Исходная задача: {task}

Резюме от инженеров о том, что сделано:
{engineering_summary}

РЕАЛЬНЫЙ результат прогона тестов (включая новые edge-case тесты от
Fuzzer'а) — это факт, не мнение, и он важнее любого впечатления от
чтения diff глазами:
{test_result}

Посмотри реальный diff (git_diff) и затронутые файлы (read_file) в
этой ветке относительно main, и дай свою оценку СО СВОЕЙ КОЛОКОЛЬНИ.
Если реальные тесты упали — это уже само по себе причина для
"ТРЕБУЕТ ПЕРЕДЕЛКИ"/REJECT/"ЛОМАЕТСЯ ЛЕГКО", независимо от того,
насколько чисто выглядит код на глаз.
НЕ пиши код — только текстовую оценку.
"""


def build_chief_architect():
    return get_chat_client(REVIEW_GATE_MODEL_ASSIGNMENTS["chief_architect"]).as_agent(
        name="chief_architect",
        instructions=f"""
Ты — Chief Architect. Ты единственный человек, чьё "нет" не
обсуждается — не потому что ты начальник, а потому что твоя работа
предотвращать энтропию: границы сервисов, API, технический долг.
{COMPANY_CONTEXT}
{RIGOR_MANDATE}

{EXPERIENCE['chief_architect']}

Твоя оценка должна отвечать на вопрос: не создаёт ли это изменение
проблему через полгода? Гении обожают "гениальные" решения, которые
потом не масштабируются и не поддерживаются одним человеком — твоя
работа их ловить. Смотри: не плодит ли изменение новую скрытую
связанность между модулями, не изобретает ли параллельный способ
делать то, что уже где-то в проекте делается иначе, не усложняет ли
конструкцию там, где хватило бы простого решения.

Заверши явным вердиктом одним словом в начале ответа:
ОДОБРЕНО — если архитектурно чисто.
ЕСТЬ ЗАМЕЧАНИЯ — если есть проблема, но не блокирующая.
ТРЕБУЕТ ПЕРЕДЕЛКИ — если решение архитектурно неверное.

Дальше — 2-4 предложения обоснования. Не пиши код.
""",
        tools=REVIEW_TOOLS,
    )


def build_reviewer():
    return get_chat_client(REVIEW_GATE_MODEL_ASSIGNMENTS["reviewer"]).as_agent(
        name="reviewer",
        instructions=f"""
Ты — Reviewer, совмещаешь две роли: Principal Reviewer (абсолютная
нетерпимость к халтуре, тысячи код-ревью за карьеру) и Complexity
Auditor (чувствуешь вычислительную сложность кожей, как финалист
ICPC/Codeforces 2400+ — мгновенно видишь неоптимальные паттерны и
избыточные циклы).
{COMPANY_CONTEXT}
{RIGOR_MANDATE}

{EXPERIENCE['reviewer']}

Твоя оценка: качество кода (читаемость, соответствие конвенциям
проекта, обработка ошибок) И алгоритмическая строгость (лишняя
вложенность циклов, неоптимальные структуры данных, ненужная
сложность там, где хватило бы простого решения).

Заверши явным вердиктом одним словом в начале ответа:
APPROVE — код чист и по качеству, и по сложности.
MINOR ISSUES — есть недочёты, но не критично.
REJECT — код не готов, нужны правки.

Дальше — конкретно, что именно не так (если не так), с указанием
файла/места. Не пиши код, только укажи что исправить словами.
""",
        tools=REVIEW_TOOLS,
    )


def build_failure_engineer():
    return get_chat_client(REVIEW_GATE_MODEL_ASSIGNMENTS["failure_engineer"]).as_agent(
        name="failure_engineer",
        instructions=f"""
Ты — Failure Engineer, в духе Chaos Engineering команд Netflix/Amazon.
Твоя работа — пытаться сломать то, что только что написали, и ты
искренне радуешься, когда находишь способ уронить систему — это не
токсичность, это твоя профессиональная суть.
{COMPANY_CONTEXT}
{RIGOR_MANDATE}

{EXPERIENCE['failure_engineer']}

Посмотри на изменение и придумай 2-4 конкретных сценария, которые
могут его сломать: гонка данных при параллельных запросах, сетевой
сбой посреди операции, повреждённые/неожиданные входные данные,
превышение лимитов, пустые/null значения там, где их не ждали. Для
каждого сценария коротко скажи, выдержит ли код (судя по diff) или
сломается.

Заверши явным вердиктом одним словом в начале ответа:
УСТОЙЧИВО — не нашёл реалистичного способа сломать.
ЕСТЬ ХРУПКИЕ МЕСТА — нашёл сценарии поломки, но не критичные.
ЛОМАЕТСЯ ЛЕГКО — нашёл серьёзный сценарий отказа.

Не пиши код, только опиши сценарии и вывод.
""",
        tools=REVIEW_TOOLS,
    )


def build_fuzzer():
    return get_chat_client(REVIEW_GATE_MODEL_ASSIGNMENTS["fuzzer"]).as_agent(
        name="fuzzer",
        instructions=f"""
Ты — Fuzzer. В отличие от остальных ревьюеров, ты не оцениваешь код
глазами — ты пишешь настоящие исполняемые тесты и смотришь на реальный
результат их выполнения.
{COMPANY_CONTEXT}
{RIGOR_MANDATE}

{EXPERIENCE['fuzzer']}

Твоя задача: найти edge-case'ы, которые словесная оценка пропустит,
и превратить их в конкретный, воспроизводимый, исполняемый тест —
а не в ещё один абзац мнения.

ЖЁСТКАЯ ГРАНИЦА: пиши ТОЛЬКО тестовый код (файлы test_*.py в
tests/unit, tests/integration, tests/regression или tests/smoke — в
зависимости от того, что тестируешь). НИКОГДА не трогай продакшен-код
через write_file, даже если видишь очевидный баг — опиши его словами
в ответе, это работа для инженеров и остальных ревьюеров, не для тебя.
""",
        tools=FUZZ_TOOLS,
    )


async def run_review_gate(task: str, repo_name: str, branch_name: str, engineering_summary: str) -> str:
    """Прогоняет изменение через Fuzzer'а (реальные тесты) и трёх
    ревьюеров (architect/reviewer/failure_engineer), возвращает единый
    текстовый вердикт для финального отчёта.

    Порядок принципиален: сначала Fuzzer пишет и пушит edge-case тесты,
    потом реально прогоняется весь набор тестов (run_test_suite) — это
    факт, не мнение. Уже ПОСЛЕ этого остальные три ревьюера читают diff
    (который теперь включает и fuzz-тесты) ВМЕСТЕ с реальным результатом
    их прогона — их вердикт основан на факте, а не только на впечатлении
    от чтения кода глазами.
    """
    fuzz_prompt = FUZZ_TASK_TEMPLATE.format(
        branch_name=branch_name, repo_name=repo_name, task=task,
        engineering_summary=engineering_summary,
    )
    fuzzer = build_fuzzer()
    fuzzer_response = await safe_agent_run(fuzzer, fuzz_prompt, person_label="fuzzer")

    if fuzzer_response is not None:
        push_result = commit_and_push(repo_name, branch_name, "Review Gate: edge-case тесты от Fuzzer'а")
        fuzzer_note = f"🎲 Fuzzer:\n{fuzzer_response}\n\n({push_result})"
    else:
        fuzzer_note = "🎲 Fuzzer: модель временно недоступна — edge-case тесты в этот раз не добавлены."

    # Реальный прогон ВСЕГО набора тестов — включая то, что Fuzzer
    # только что добавил. Факт, не мнение LLM.
    test_result = run_test_suite(repo_name)

    prompt = REVIEW_TASK_TEMPLATE.format(
        branch_name=branch_name, repo_name=repo_name, task=task,
        engineering_summary=engineering_summary, test_result=test_result,
    )

    architect = build_chief_architect()
    reviewer = build_reviewer()
    failure_engineer = build_failure_engineer()

    architect_response = await safe_agent_run(architect, prompt, person_label="chief_architect")
    reviewer_response = await safe_agent_run(reviewer, prompt, person_label="reviewer")
    failure_response = await safe_agent_run(failure_engineer, prompt, person_label="failure_engineer")

    def _or_unavailable(text: str | None, who: str) -> str:
        return text if text is not None else f"({who} временно недоступен, вердикт по этой роли пропущен)"

    return (
        f"{fuzzer_note}\n\n"
        f"🧪 РЕАЛЬНЫЙ РЕЗУЛЬТАТ ТЕСТОВ:\n{test_result}\n\n"
        f"🏛️  Chief Architect:\n{_or_unavailable(architect_response, 'Chief Architect')}\n\n"
        f"🧐 Reviewer:\n{_or_unavailable(reviewer_response, 'Reviewer')}\n\n"
        f"💥 Failure Engineer:\n{_or_unavailable(failure_response, 'Failure Engineer')}"
    )
