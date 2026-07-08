"""
Главный сценарий:

1. clone_or_update_repos() — синхронизируем оба репо локально.
2. Topic Scout (на code-модели) смотрит git_log обоих репозиториев,
   выбирает последний содержательный коммит/изменение и формулирует
   ОДИН конкретный спорный вопрос для команды (не "обсудите проект",
   а "вот это изменение в L7 — это решение или забытый баг?").
3. Запускается GroupChat: CTO, Backend Senior, Product/Frontend,
   QA/Security обсуждают этот вопрос. Модератор (отдельный Agent)
   решает, кто говорит следующим — без жёсткого round-robin,
   ориентируясь на то, кто реально хочет/должен ответить дальше.
4. Дискуссия останавливается по term. условию (число сообщений)
   ИЛИ когда модератор решает, что пришли к выводу.
"""

import asyncio

from agent_framework import Message
from agent_framework.orchestrations import GroupChatBuilder

from agents.team import build_team
from config.client_factory import get_chat_client
from config.models import MODEL_ASSIGNMENTS
from tools.repo_tools import git_log
from workflows._common import ask, extract_messages, sync_repos_or_alert

MAX_MESSAGES = 24  # защита от бесконечного спора / траты кредитов


async def find_discussion_topic() -> str:
    """Отдельный лёгкий вызов модели (не входит в группу), который
    смотрит git log обоих репозиториев и формулирует один конкретный
    вопрос для обсуждения командой."""
    scout_client = get_chat_client(MODEL_ASSIGNMENTS["code_scout"])

    bld_system_log = git_log("bld-system", limit=15)
    bld_panel_log = git_log("bld-panel", limit=15)

    prompt = f"""
Вот последние коммиты в двух репозиториях проекта BLD System.

=== bld-system ===
{bld_system_log}

=== bld-panel ===
{bld_panel_log}

Выбери ОДИН коммит или одно изменение, которое выглядит спорным,
рискованным, недоделанным или интересным с архитектурной/продуктовой
точки зрения. Сформулируй ОДНО конкретное предложение-вопрос для
обсуждения командой (CTO, Backend Senior, Product/Frontend, QA/Security).

Вопрос должен быть конкретным и привязанным к репозиторию и коммиту,
например: "В bld-system, коммит abc123 меняет логику L7 — это
осознанное решение или забытый edge-case? Нужно обсудить."

Ответь ТОЛЬКО самим вопросом, без преамбулы.
"""
    return await ask(scout_client, prompt)


def build_discussion_workflow(team: dict):
    """Собирает GroupChat workflow с модератором-агентом."""
    moderator_client = get_chat_client(MODEL_ASSIGNMENTS["moderator"])
    moderator_agent = moderator_client.as_agent(
        name="moderator",
        instructions="""
Ты — модератор технического обсуждения. У тебя НЕТ своего мнения
о проекте, твоя единственная задача — после каждого сообщения решать,
кто из участников (cto, backend_senior, product_frontend, qa_security)
должен ответить следующим.

Правила выбора:
- Если кого-то явно упомянули по имени или роли — выбирай его.
- Если кто-то задал прямой вопрос — выбирай того, к кому он адресован.
- Если в последнем сообщении есть утверждение, которое противоречит
  зоне ответственности другого участника — дай ему слово, чтобы он
  мог возразить.
- Не давай одному и тому же участнику говорить три раза подряд без
  необходимости.
- Если обсуждение явно пришло к согласию или зашло в тупик —
  заверши разговор.
""",
    )

    def stop_condition(messages: list[Message]) -> bool:
        assistant_messages = [m for m in messages if m.role == "assistant"]
        return len(assistant_messages) >= MAX_MESSAGES

    return (
        GroupChatBuilder(
            participants=list(team.values()),
            orchestrator_agent=moderator_agent,
            termination_condition=stop_condition,
        )
        .build()
    )


async def main():
    print("Синхронизация репозиториев...")
    if not await sync_repos_or_alert():
        return

    print("\nИщем повод для дискуссии в git log...")
    topic = await find_discussion_topic()
    print(f"\nТема дискуссии:\n{topic}\n")
    print("=" * 80)

    team = build_team()
    workflow = build_discussion_workflow(team)

    try:
        result = await workflow.run(topic)
        messages = extract_messages(result.get_outputs())
    except Exception as e:
        print(f"GroupChat упал с ошибкой (известный edge-case библиотеки agent_framework): {e}")
        print("Дискуссия не состоялась в этот раз.")
        return

    print("\n" + "=" * 80)
    print("ХОД ДИСКУССИИ:\n")
    for msg in messages:
        if msg.role == "assistant":
            print(f"\n[{msg.author_name or 'system'}]: {msg.text}")

    print("\n" + "=" * 80)
    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())
