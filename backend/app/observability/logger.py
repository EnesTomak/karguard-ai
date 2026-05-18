"""Observability logger facade."""

from __future__ import annotations

from app.core.logging import get_logger


def get_observability_logger(name: str):
    """Return application logger for observability modules."""
    return get_logger(name)
