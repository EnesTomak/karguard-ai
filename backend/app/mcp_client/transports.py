"""Transport abstractions for MCP client gateway."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any, Protocol

from app.mcp_client.registry import get_tool_callable


class MCPTransport(Protocol):
    """Protocol for MCP tool transport implementations."""

    async def call_tool(self, server: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        ...


class InProcessMCPTransport:
    """Current P0 transport that routes tools in-process via registry."""

    def __init__(self, resolver: Callable[[str, str], Callable[..., Any]] | None = None) -> None:
        self._resolver = resolver or get_tool_callable

    async def call_tool(self, server: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        tool_callable = self._resolver(server, tool_name)
        if inspect.iscoroutinefunction(tool_callable):
            return await tool_callable(**arguments)
        return await asyncio.to_thread(tool_callable, **arguments)


class StdioMCPTransport:
    """Planned production transport."""

    async def call_tool(self, server: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        raise NotImplementedError(
            "StdioMCPTransport is planned for production transport integration."
        )
