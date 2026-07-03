"""
Создаёт chat client для конкретного deployment в Azure AI Foundry.

Использует FoundryChatClient из agent_framework.foundry (актуальный путь
в реальном пакете agent-framework — НЕ agent_framework.azure, это была
ошибка в более ранней версии кода).

Аутентификация через DefaultAzureCredential: локально это значит, что
должен быть выполнен `az login` заранее; в GitHub Actions — что заданы
AZURE_CLIENT_ID/AZURE_TENANT_ID/AZURE_CLIENT_SECRET (Service Principal),
DefaultAzureCredential подхватывает их автоматически из окружения.
"""

from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

from config.models import FOUNDRY_PROJECT_ENDPOINT

_credential = DefaultAzureCredential()


def get_chat_client(deployment_name: str) -> FoundryChatClient:
    """Возвращает FoundryChatClient, настроенный на конкретный deployment.

    Важно: параметр называется `model` в конструкторе FoundryChatClient
    (а не `deployment_name`), но по смыслу это ровно то же самое —
    имя deployment'а, которое ты задал при деплое модели в Foundry.
    """
    if not FOUNDRY_PROJECT_ENDPOINT:
        raise RuntimeError(
            "FOUNDRY_PROJECT_ENDPOINT не задан. "
            "Укажи его в .env (см. .env.example)."
        )
    return FoundryChatClient(
        project_endpoint=FOUNDRY_PROJECT_ENDPOINT,
        model=deployment_name,
        credential=_credential,
    )

