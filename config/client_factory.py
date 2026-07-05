"""
Создаёт chat client для конкретного deployment в Azure AI Foundry.

ВАЖНО — два разных способа обращения к одному и тому же ресурсу Foundry:

1. Настоящие Azure OpenAI модели (gpt-*) — через FoundryChatClient
   (agent_framework.foundry), который использует Agent Service API
   ("проектный" эндпоинт .../api/projects/...). Это фактически формат
   Responses API — надёжно работает ТОЛЬКО с настоящими Azure OpenAI
   моделями.

2. Сторонние модели каталога (DeepSeek, Grok, Kimi, Mistral, Qwen и
   т.д.) — через Azure AI Model Inference API, унифицированный
   chat-completions эндпоинт (.../models/chat/completions) на ТОМ ЖЕ
   ресурсе Foundry. Это другая "дверь" в тот же ресурс, не другой
   проект и не другой Azure-аккаунт. Используем OpenAIChatCompletionClient
   (agent_framework_openai) с вручную настроенным AsyncOpenAI клиентом,
   потому что этот путь требует query-параметр api-version, который
   generic base_url-роутинг не добавляет автоматически.

Выбор клиента — по префиксу имени модели: всё что начинается на "gpt-"
идёт через (1), всё остальное — через (2).
"""

from agent_framework.foundry import FoundryChatClient
from agent_framework_openai import OpenAIChatCompletionClient
from azure.identity import DefaultAzureCredential
from openai import AsyncOpenAI

from config.models import FOUNDRY_PROJECT_ENDPOINT

_credential = DefaultAzureCredential()

# Модели с этими префиксами считаются настоящими Azure OpenAI —
# идут через FoundryChatClient (Responses API).
_GPT_FAMILY_PREFIXES = ("gpt-", "o1", "o3", "o4")

# Версия Azure AI Model Inference API. Актуальная стабильная на момент
# написания — при необходимости можно переопределить через env.
_INFERENCE_API_VERSION = "2024-05-01-preview"


def _inference_endpoint() -> str:
    """Выводит базовый endpoint ресурса AI Services из
    FOUNDRY_PROJECT_ENDPOINT (у которого формат
    https://<resource>.services.ai.azure.com/api/projects/<project>),
    отбрасывая '/api/projects/...' — получаем
    https://<resource>.services.ai.azure.com — и добавляем /models.
    Это не отдельная настройка, а тот же самый ресурс Foundry."""
    base = FOUNDRY_PROJECT_ENDPOINT.split("/api/projects/")[0].rstrip("/")
    return f"{base}/models"


def get_chat_client(deployment_name: str):
    """Возвращает chat client, настроенный на конкретный deployment —
    FoundryChatClient для gpt-моделей, OpenAIChatCompletionClient
    (через Model Inference API) для всех остальных."""

    if not FOUNDRY_PROJECT_ENDPOINT:
        raise RuntimeError(
            "FOUNDRY_PROJECT_ENDPOINT не задан. "
            "Укажи его в .env (см. .env.example)."
        )

    if deployment_name.startswith(_GPT_FAMILY_PREFIXES):
        # Настоящая Azure OpenAI модель — через Agent Service (Responses API).
        return FoundryChatClient(
            project_endpoint=FOUNDRY_PROJECT_ENDPOINT,
            model=deployment_name,
            credential=_credential,
        )

    # Сторонняя модель каталога — через Azure AI Model Inference API.
    import os

    api_key = os.getenv("AZURE_AI_INFERENCE_KEY", "")
    if not api_key:
        raise RuntimeError(
            f"Модель '{deployment_name}' не из линейки gpt-*/o-серии — "
            "для неё нужен Azure AI Model Inference API, а переменная "
            "AZURE_AI_INFERENCE_KEY не задана. Возьми API-ключ ресурса "
            "в Azure Portal → bld-ai-foundr → Keys and Endpoint, и добавь "
            "как секрет AZURE_AI_INFERENCE_KEY."
        )

    raw_client = AsyncOpenAI(
        base_url=_inference_endpoint(),
        api_key=api_key,
        default_query={"api-version": _INFERENCE_API_VERSION},
    )
    return OpenAIChatCompletionClient(model=deployment_name, async_client=raw_client)
