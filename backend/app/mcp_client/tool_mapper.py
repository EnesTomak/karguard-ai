"""Registry-backed tool mapper helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.mcp_client.registry import get_tool_callable, list_servers, list_tools


def resolve_tool(server: str, tool_name: str) -> Callable[..., Any]:
    """Resolve a tool callable from registry."""
    return get_tool_callable(server, tool_name)


def available_servers() -> list[str]:
    return list_servers()


def available_tools(server: str) -> list[str]:
    return list_tools(server)
