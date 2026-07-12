"""
Review Gate — проверка результата инженерной задачи ПЕРЕД тем как
отчёт уйдёт Валику. Это то, чего не хватало: раньше отчёт "инженерная
задача выполнена" уходил сразу после коммита, без единой проверки.
Теперь между "код написан" и "отчёт отправлен" стоит настоящий gate —
как в реальных компаниях.

Три роли, три разных угла:
- Chief Architect — архитектурное вето. "Его 'нет' не обсуждается":
  не управляет людьми, владеет границами архитектуры и техническим
  долгом. Смотрит НЕ на "работает ли", а на "не создаёт ли это
  проблему через полгода".
- Reviewer — объединяет Principal Reviewer (approve/reject по
  качеству кода) и Complexity Auditor (алгоритмическая строгость,
  Big O, лишняя сложность) в одну практичную роль код-ревьюера.
- Failure Engineer — Chaos Engineering по духу: специально пытается
  сломать то, что только что написали. Радуется, когда находит, как
  уронить систему — это его работа, а не баг характера.

ВАЖНО: они только ЧИТАЮТ (git_diff, read_file и т.д.), НЕ пишут код —
их роль оценивать, а не переписывать за инженеров.
"""

from config.client_factory import get_chat_client
from config.models import REVIEW_GATE_MODEL_ASSIGNMENTS
from tools.repo_tools import git_diff, git_log, grep_repo, list_repo_files, read_file

REVIEW_TOOLS = [list_repo_files, read_file, git_log, git_diff, grep_repo]

from agents._shared_context import RIGOR_MANDATE, load_bld_scope_context

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
}

REVIEW_TASK_TEMPLATE = """
Инженерная команда только что написала код по задаче и запушила его
в ветку "{branch_name}" репозитория "{repo_name}" (НЕ в main).

Исходная задача: {task}

Резюме от инженеров о том, что сделано:
{engineering_summary}

Посмотри реальный diff (git_diff) и затронутые файлы (read_file) в
этой ветке относительно main, и дай свою оценку СО СВОЕЙ КОЛОКОЛЬНИ.
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


async def run_review_gate(task: str, repo_name: str, branch_name: str, engineering_summary: str) -> str:
    """Прогоняет изменение через всех трёх ревьюеров и возвращает
    единый текстовый вердикт для финального отчёта."""
    prompt = REVIEW_TASK_TEMPLATE.format(
        branch_name=branch_name, repo_name=repo_name, task=task,
        engineering_summary=engineering_summary,
    )

    architect = build_chief_architect()
    reviewer = build_reviewer()
    failure_engineer = build_failure_engineer()

    architect_response = await architect.run(prompt)
    reviewer_response = await reviewer.run(prompt)
    failure_response = await failure_engineer.run(prompt)

    return (
        f"🏛️  Chief Architect:\n{architect_response.text.strip()}\n\n"
        f"🧐 Reviewer:\n{reviewer_response.text.strip()}\n\n"
        f"💥 Failure Engineer:\n{failure_response.text.strip()}"
    )
