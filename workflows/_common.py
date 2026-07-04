"""
Общие вспомогательные функции для всех workflow (discussion,
board_meeting, executive_meeting, office_chat) — чтобы не дублировать
одно и то же в нескольких местах.
"""

from typing import Any

from agent_framework import Message


async def ask(client, prompt: str) -> str:
    """Одноразовый текстовый запрос к модели, без tools и без истории."""
    response = await client.get_response([Message(role="user", contents=[prompt])])
    return response.text.strip()


def extract_messages(outputs: list[Any]) -> list[Message]:
    """Разворачивает результат workflow.run(...).get_outputs() в плоский
    список Message."""
    result: list[Message] = []
    for item in outputs:
        if isinstance(item, Message):
            result.append(item)
        elif isinstance(item, (list, tuple)):
            result.extend(extract_messages(item))
    return result
