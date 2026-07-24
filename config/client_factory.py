"""
Создаёт chat client для конкретного имени модели.

Два независимых провайдера, выбираются переменной окружения
MODEL_PROVIDER (см. .env.example):

1. MODEL_PROVIDER=openai (значение по умолчанию для нового форка проекта) —
   ЛЮБОЙ OpenAI-совместимый endpoint: сам api.openai.com, или OpenRouter,
   Groq, Together, локальный vLLM/Ollama и т.д. — всё, что говорит на
   Chat Completions API. Нужен только OPENAI_API_KEY (+ опционально
   OPENAI_BASE_URL, если это не сам OpenAI). Это самый низкий порог входа:
   никакого Azure-аккаунта, deployment'ов или az login — просто ключ.

2. MODEL_PROVIDER=azure_foundry — оригинальная настройка автора этого
   форка (Azure AI Foundry). Сохранена как есть, чтобы существующие
   деплойменты (в т.ч. GitHub Actions с уже настроенными Azure-секретами)
   продолжали работать без изменений. Два разных способа обращения к
   одному и тому же ресурсу Foundry:
   a) Настоящие Azure OpenAI модели (gpt-*, o1/o3/o4) — через
      FoundryChatClient (Agent Service / Responses API).
   b) Сторонние модели каталога (DeepSeek, Grok, Kimi, Mistral и т.д.) —
      через Azure AI Model Inference API (унифицированный
      chat-completions эндпоинт на том же ресурсе), нужен
      AZURE_AI_INFERENCE_KEY.

Если это твой собственный форк и тебе не нужен Azure — можно вообще не
трогать этот файл, достаточно оставить MODEL_PROVIDER=openai (или не
задавать его, это дефолт) и указать OPENAI_API_KEY.
"""

import os

from agent_framework_openai import OpenAIChatCompletionClient
from openai import AsyncOpenAI

MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "openai").strip().lower()


# ============================================================
# Провайдер 1 (по умолчанию): любой OpenAI-совместимый endpoint.
# ============================================================

def _openai_compatible_client(model_name: str):
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY не задан. Укажи его в .env (см. .env.example) — "
            "подойдёт ключ с platform.openai.com, или ключ любого другого "
            "OpenAI-совместимого провайдера (OpenRouter, Groq, локальный "
            "vLLM/Ollama и т.д.), если вместе с ним задан OPENAI_BASE_URL."
        )
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    raw_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return OpenAIChatCompletionClient(model=model_name, async_client=raw_client)


# ============================================================
# Провайдер 2: Azure AI Foundry (настройка автора форка).
# ============================================================

_GPT_FAMILY_PREFIXES = ("gpt-", "o1", "o3", "o4")
_INFERENCE_API_VERSION = "2024-05-01-preview"


def _azure_foundry_client(deployment_name: str):
    from agent_framework.foundry import FoundryChatClient
    from azure.identity import DefaultAzureCredential

    from config.models import FOUNDRY_PROJECT_ENDPOINT

    if not FOUNDRY_PROJECT_ENDPOINT:
        raise RuntimeError(
            "FOUNDRY_PROJECT_ENDPOINT не задан. "
            "Укажи его в .env (см. .env.example)."
        )

    if deployment_name.startswith(_GPT_FAMILY_PREFIXES):
        return FoundryChatClient(
            project_endpoint=FOUNDRY_PROJECT_ENDPOINT,
            model=deployment_name,
            credential=DefaultAzureCredential(),
        )

    api_key = os.getenv("AZURE_AI_INFERENCE_KEY", "")
    if not api_key:
        raise RuntimeError(
            f"Модель '{deployment_name}' не из линейки gpt-*/o-серии — "
            "для неё нужен Azure AI Model Inference API, а переменная "
            "AZURE_AI_INFERENCE_KEY не задана."
        )
    base = FOUNDRY_PROJECT_ENDPOINT.split("/api/projects/")[0].rstrip("/")
    raw_client = AsyncOpenAI(
        base_url=f"{base}/models",
        api_key=api_key,
        default_query={"api-version": _INFERENCE_API_VERSION},
    )
    return OpenAIChatCompletionClient(model=deployment_name, async_client=raw_client)


def get_chat_client(deployment_name: str):
    """Возвращает chat client для указанного имени модели — маршрутизация
    по MODEL_PROVIDER (см. docstring модуля)."""
    if MODEL_PROVIDER == "azure_foundry":
        return _azure_foundry_client(deployment_name)
    if MODEL_PROVIDER != "openai":
        raise RuntimeError(
            f"Неизвестный MODEL_PROVIDER='{MODEL_PROVIDER}'. "
            "Допустимые значения: 'openai' (дефолт) или 'azure_foundry'."
        )
    return _openai_compatible_client(deployment_name)
