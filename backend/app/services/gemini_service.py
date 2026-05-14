"""Gemini AI service wrappers.

Includes:
- structured JSON generation
- free-form text generation
- tool/function-calling generation (Python SDK automatic function calling)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None

MAX_RETRIES = 3
BASE_DELAY = 5  # seconds


def get_client() -> genai.Client:
    """Lazy-initialize Gemini client."""
    global _client
    if _client is None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is missing. Add it to .env.")
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


async def _call_with_retry(fn, *args, **kwargs):
    """Call Gemini API with exponential backoff on rate-limit errors."""
    for attempt in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            error_str = str(exc)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                delay = BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Rate limit hit. Retrying in %ss (attempt %s/%s).",
                    delay,
                    attempt + 1,
                    MAX_RETRIES,
                )
                await asyncio.sleep(delay)
            else:
                raise
    return fn(*args, **kwargs)


async def generate_structured(
    prompt: str,
    response_schema: Any,
    system_instruction: str | None = None,
    temperature: float = 0.3,
) -> dict:
    """Call Gemini with structured JSON output."""
    client = get_client()

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=response_schema,
        temperature=temperature,
    )
    if system_instruction:
        config.system_instruction = system_instruction

    response = await _call_with_retry(
        client.models.generate_content,
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=config,
    )

    if not response.text:
        logger.error("Gemini returned an empty structured response.")
        return {}
    return json.loads(response.text)


async def generate_text(
    prompt: str,
    system_instruction: str | None = None,
    temperature: float = 0.5,
) -> str:
    """Call Gemini for free-form text output."""
    client = get_client()

    config = types.GenerateContentConfig(temperature=temperature)
    if system_instruction:
        config.system_instruction = system_instruction

    response = await _call_with_retry(
        client.models.generate_content,
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=config,
    )
    return response.text or ""


async def generate_text_with_tools(
    prompt: str,
    tools: list[Any],
    system_instruction: str | None = None,
    temperature: float = 0.3,
    force_any_function: bool = False,
    allowed_function_names: list[str] | None = None,
) -> str:
    """Call Gemini with tool/function-calling enabled.

    The Python SDK automatically handles:
    1) detecting function calls
    2) executing the Python callables in `tools`
    3) feeding function results back to the model
    4) returning final response text
    """
    client = get_client()

    config = types.GenerateContentConfig(
        temperature=temperature,
        tools=tools,
    )
    if system_instruction:
        config.system_instruction = system_instruction

    if force_any_function:
        config.tool_config = types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.ANY,
                allowed_function_names=allowed_function_names or [],
            )
        )

    response = await _call_with_retry(
        client.models.generate_content,
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=config,
    )
    return response.text or ""
