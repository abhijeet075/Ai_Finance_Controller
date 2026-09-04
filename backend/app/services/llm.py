"""Guarded OpenAI-compatible LLM client used only after deterministic controls."""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import get_settings


class LLMUnavailableError(RuntimeError):
    pass


def complete_json(system: str, user: str, schema_name: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.llm_api_key or not settings.llm_model:
        raise LLMUnavailableError("LLM is not configured.")
    payload = {
        "model": settings.llm_model,
        "temperature": 0,
        "max_tokens": settings.llm_max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
        response = client.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
    try:
        content = response.json()["choices"][0]["message"]["content"]
        result = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise LLMUnavailableError(f"Invalid {schema_name} response from LLM.") from exc
    if not isinstance(result, dict):
        raise LLMUnavailableError(f"Invalid {schema_name} response from LLM.")
    return result
