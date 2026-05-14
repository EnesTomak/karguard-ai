"""Gemini AI Service — Client wrapper for Google Gemini API.

Uses google-genai SDK with structured JSON output.
Includes retry logic with exponential backoff for rate limits.
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

# ── Client singleton ──────────────────────────────────

_client: genai.Client | None = None

MAX_RETRIES = 3
BASE_DELAY = 5  # seconds


def get_client() -> genai.Client:
    """Lazy-initialize Gemini client."""
    global _client
    if _client is None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY ayarlanmamış. .env dosyasına ekleyin."
            )
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


# ── Retry helper ──────────────────────────────────────

async def _call_with_retry(fn, *args, **kwargs):
    """Call a function with exponential backoff on 429 errors."""
    for attempt in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                delay = BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"Rate limit aşıldı. {delay}s sonra tekrar denenecek... "
                    f"(deneme {attempt + 1}/{MAX_RETRIES})"
                )
                await asyncio.sleep(delay)
            else:
                raise
    # Final attempt without catching
    return fn(*args, **kwargs)


# ── Structured generation ─────────────────────────────

async def generate_structured(
    prompt: str,
    response_schema: Any,
    system_instruction: str | None = None,
    temperature: float = 0.3,
) -> dict:
    """Call Gemini with structured JSON output.

    Args:
        prompt: The user prompt.
        response_schema: A Pydantic model class for the response structure.
        system_instruction: Optional system instruction.
        temperature: Generation temperature (lower = more deterministic).

    Returns:
        Parsed dict matching the response_schema.
    """
    client = get_client()

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=response_schema,
        temperature=temperature,
    )

    if system_instruction:
        config.system_instruction = system_instruction

    try:
        response = await _call_with_retry(
            client.models.generate_content,
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=config,
        )

        if not response.text:
            logger.error("Gemini boş yanıt döndü.")
            return {}

        return json.loads(response.text)

    except Exception as e:
        logger.error(f"Gemini API hatası: {e}")
        raise


# ── Free-form generation ──────────────────────────────

async def generate_text(
    prompt: str,
    system_instruction: str | None = None,
    temperature: float = 0.5,
) -> str:
    """Call Gemini for free-form text output."""
    client = get_client()

    config = types.GenerateContentConfig(
        temperature=temperature,
    )

    if system_instruction:
        config.system_instruction = system_instruction

    try:
        response = await _call_with_retry(
            client.models.generate_content,
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
        return response.text or ""

    except Exception as e:
        logger.error(f"Gemini API hatası: {e}")
        raise
