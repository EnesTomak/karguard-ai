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
from pydantic import ValidationError

from app.config import settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None

def _extract_json_payload(text: str) -> dict[str, Any]:
    """Parse structured output robustly even if extra text leaks in."""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            raise ValueError("Structured response is not valid JSON.") from exc

    raise ValueError("Structured response does not include a JSON object.")


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
    max_retries = max(0, settings.GEMINI_MAX_RETRIES)
    base_delay = max(1, settings.GEMINI_BASE_DELAY_SECONDS)
    timeout_seconds = max(5, settings.GEMINI_CALL_TIMEOUT_SECONDS)
    for attempt in range(max_retries):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(fn, *args, **kwargs),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "Gemini call timed out. Retrying in %ss (attempt %s/%s).",
                delay,
                attempt + 1,
                max_retries + 1,
            )
            await asyncio.sleep(delay)
        except Exception as exc:
            error_str = str(exc)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "Rate limit hit. Retrying in %ss (attempt %s/%s).",
                    delay,
                    attempt + 1,
                    max_retries + 1,
                )
                await asyncio.sleep(delay)
            else:
                raise
    return await asyncio.wait_for(
        asyncio.to_thread(fn, *args, **kwargs),
        timeout=timeout_seconds,
    )


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
        raise RuntimeError("Gemini returned an empty structured response.")

    payload = _extract_json_payload(response.text)

    # Enforce schema validation to prevent silent contract drift.
    if hasattr(response_schema, "model_validate"):
        try:
            validated = response_schema.model_validate(payload)
            if hasattr(validated, "model_dump"):
                return validated.model_dump()
            return payload
        except ValidationError as exc:
            logger.error("Gemini structured output failed schema validation: %s", exc)
            raise

    return payload


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
