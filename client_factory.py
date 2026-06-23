"""
Создаёт chat client для конкретного deployment в Azure AI Foundry.

Использует FoundryChatClient — он создаёт агентов локально (не как
server-managed ресурсы), что идеально подходит для orchestration-паттернов
(GroupChat, Handoff, Sequential, Concurrent), как и рекомендует
официальная документация Agent Framework.

Аутентификация через DefaultAzureCredential: на твоей машине это значит,
что должен быть выполнен `az login` заранее (или настроены env vars для
Managed Identity / Service Principal, если будешь деплоить в облако).
"""

from agent_framework.azure import FoundryChatClient
from azure.identity import DefaultAzureCredential

from config.models import FOUNDRY_PROJECT_ENDPOINT

_credential = DefaultAzureCredential()


def get_chat_client(deployment_name: str) -> FoundryChatClient:
    if not FOUNDRY_PROJECT_ENDPOINT:
        raise RuntimeError(
            "FOUNDRY_PROJECT_ENDPOINT не задан. "
            "Укажи его в .env (см. .env.example)."
        )
    return FoundryChatClient(
        project_endpoint=FOUNDRY_PROJECT_ENDPOINT,
        deployment_name=deployment_name,
        credential=_credential,
    )
