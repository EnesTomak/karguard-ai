"""Gemini AI service wrappers.

Includes:
- structured JSON generation
- free-form text generation
- tool/function-calling generation
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from app.config import settings

logger = logging.getLogger(__name__)

_client: Any | None = None
_genai_module: Any | None = None
_genai_types_module: Any | None = None


def get_genai_module() -> Any:
    """Return the Google Gen AI SDK module, loading it lazily.

    Keeping this import lazy has two benefits:
    1) the app can still boot in DEMO_OFFLINE_MODE without google-genai installed;
    2) Pyrefly/Pylance will not fail at module import time on machines where the
       selected interpreter is missing the package.
    """
    global _genai_module

    if _genai_module is None:
        try:
            _genai_module = importlib.import_module("google.genai")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "google-genai is not installed in the selected Python environment. "
                "Install it with: python -m pip install -U google-genai"
            ) from exc

    return _genai_module


def get_genai_types() -> Any:
    """Return google.genai.types lazily."""
    global _genai_types_module

    if _genai_types_module is None:
        try:
            _genai_types_module = importlib.import_module("google.genai.types")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "google-genai is not installed in the selected Python environment. "
                "Install it with: python -m pip install -U google-genai"
            ) from exc

    return _genai_types_module


def _extract_json_payload(text: str) -> dict[str, Any]:
    """Parse structured JSON robustly, even if markdown fences leak in."""
    cleaned = text.strip()

    fenced_match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        cleaned = fenced_match.group(1).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            raise ValueError("Structured response is not valid JSON.") from exc

    raise ValueError("Structured response does not include a JSON object.")


def get_client() -> Any:
    """Lazy-initialize Gemini client."""
    global _client

    if _client is None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is missing. Add it to .env.")

        genai = get_genai_module()
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)

    return _client


def reset_client() -> None:
    """Reset the cached Gemini client. Useful in tests after changing settings."""
    global _client
    _client = None


def _is_retryable_error(exc: Exception) -> bool:
    error_text = str(exc)
    retryable_markers = (
        "429",
        "RESOURCE_EXHAUSTED",
        "rate limit",
        "deadline",
        "timeout",
        "temporarily unavailable",
        "503",
    )
    return any(marker.lower() in error_text.lower() for marker in retryable_markers)


async def _call_with_retry(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call Gemini API with bounded retry + timeout."""
    max_retries = max(0, int(getattr(settings, "GEMINI_MAX_RETRIES", 2)))
    base_delay = max(1, int(getattr(settings, "GEMINI_BASE_DELAY_SECONDS", 2)))
    timeout_seconds = max(5, int(getattr(settings, "GEMINI_CALL_TIMEOUT_SECONDS", 60)))

    for attempt in range(max_retries + 1):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(fn, *args, **kwargs),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            if attempt >= max_retries:
                raise RuntimeError("Gemini call timed out after all retries.") from exc

            delay = base_delay * (2**attempt)
            logger.warning(
                "Gemini call timed out. Retrying in %ss (attempt %s/%s).",
                delay,
                attempt + 1,
                max_retries + 1,
            )
            await asyncio.sleep(delay)
        except Exception as exc:
            if not _is_retryable_error(exc) or attempt >= max_retries:
                raise

            delay = base_delay * (2**attempt)
            logger.warning(
                "Gemini transient error. Retrying in %ss (attempt %s/%s): %s",
                delay,
                attempt + 1,
                max_retries + 1,
                exc,
            )
            await asyncio.sleep(delay)

    # Defensive: loop always returns or raises.
    raise RuntimeError("Gemini call failed unexpectedly.")


def _coerce_structured_response(response: Any, response_schema: Any) -> dict[str, Any]:
    """Extract and validate a structured response from the Gen AI SDK response."""
    parsed_response = getattr(response, "parsed", None)

    if parsed_response is not None:
        if isinstance(parsed_response, BaseModel):
            payload: dict[str, Any] = parsed_response.model_dump()
        elif isinstance(parsed_response, dict):
            payload = parsed_response
        else:
            payload = _extract_json_payload(str(parsed_response))
    else:
        if not getattr(response, "text", None):
            raise RuntimeError("Gemini returned an empty structured response.")
        payload = _extract_json_payload(response.text)

    if hasattr(response_schema, "model_validate"):
        try:
            validated = response_schema.model_validate(payload)
        except ValidationError:
            logger.exception("Gemini structured output failed schema validation.")
            raise

        if hasattr(validated, "model_dump"):
            return validated.model_dump()

    return payload


async def generate_structured(
    prompt: str,
    response_schema: Any,
    system_instruction: str | None = None,
    temperature: float = 0.3,
) -> dict[str, Any]:
    """Call Gemini with structured JSON output."""
    client = get_client()
    types = get_genai_types()

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
    return _coerce_structured_response(response, response_schema)


async def generate_structured_with_tools(
    prompt: str,
    response_schema: Any,
    tools: list[Any],
    system_instruction: str | None = None,
    temperature: float = 0.1,
    force_any_function: bool = False,
    allowed_function_names: list[str] | None = None,
) -> dict[str, Any]:
    """Call Gemini with structured JSON output and function calling enabled."""
    client = get_client()
    types = get_genai_types()

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=response_schema,
        temperature=temperature,
        tools=tools,
    )
    if system_instruction:
        config.system_instruction = system_instruction

    if force_any_function:
        function_config = types.FunctionCallingConfig(
            mode=types.FunctionCallingConfigMode.ANY,
        )
        if allowed_function_names:
            function_config.allowed_function_names = allowed_function_names

        config.tool_config = types.ToolConfig(
            function_calling_config=function_config,
        )

    response = await _call_with_retry(
        client.models.generate_content,
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=config,
    )
    return _coerce_structured_response(response, response_schema)


async def generate_text(
    prompt: str,
    system_instruction: str | None = None,
    temperature: float = 0.5,
) -> str:
    """Call Gemini for free-form text output."""
    client = get_client()
    types = get_genai_types()

    config = types.GenerateContentConfig(temperature=temperature)
    if system_instruction:
        config.system_instruction = system_instruction

    response = await _call_with_retry(
        client.models.generate_content,
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=config,
    )
    return getattr(response, "text", None) or ""


async def generate_text_with_tools(
    prompt: str,
    tools: list[Any],
    system_instruction: str | None = None,
    temperature: float = 0.3,
    force_any_function: bool = False,
    allowed_function_names: list[str] | None = None,
) -> str:
    """Call Gemini with tool/function-calling enabled.

    The Python SDK can automatically detect function calls, execute Python
    callables in `tools`, feed results back to the model, and return final text.
    """
    client = get_client()
    types = get_genai_types()

    config = types.GenerateContentConfig(
        temperature=temperature,
        tools=tools,
    )
    if system_instruction:
        config.system_instruction = system_instruction

    if force_any_function:
        function_config = types.FunctionCallingConfig(
            mode=types.FunctionCallingConfigMode.ANY,
        )
        if allowed_function_names:
            function_config.allowed_function_names = allowed_function_names

        config.tool_config = types.ToolConfig(
            function_calling_config=function_config,
        )

    response = await _call_with_retry(
        client.models.generate_content,
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=config,
    )
    return getattr(response, "text", None) or ""
