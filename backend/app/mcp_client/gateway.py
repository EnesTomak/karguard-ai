"""Central MCP client gateway for tool routing and tracing."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from time import perf_counter
from typing import Any, Literal

from app.mcp_client.audit import record_tool_trace
from app.mcp_client.registry import get_tool_callable
from app.mcp_client.schemas import MCPToolCallRequest, MCPToolCallResult, MCPToolTrace

logger = logging.getLogger(__name__)


class MCPClientGateway:
    """Central gateway that routes tool calls and records traces."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        resolver: Callable[[str, str], Callable[..., Any]] | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._resolver = resolver or get_tool_callable

    async def _execute_tool(self, tool_callable: Callable[..., Any], arguments: dict[str, Any]) -> Any:
        if inspect.iscoroutinefunction(tool_callable):
            return await tool_callable(**arguments)
        return await asyncio.to_thread(tool_callable, **arguments)

    async def call_tool(
        self,
        server: str,
        tool_name: str,
        arguments: dict[str, Any],
        run_id: str | None = None,
        agent_name: str | None = None,
        step_name: str | None = None,
    ) -> MCPToolCallResult:
        """Route MCP tool call through a central, traceable gateway."""
        request = MCPToolCallRequest(
            run_id=run_id,
            agent_name=agent_name,
            step_name=step_name,
            server=server,
            tool_name=tool_name,
            arguments=arguments,
        )

        started = perf_counter()
        status: Literal["success", "error"] = "success"
        payload: Any | None = None
        error_message: str | None = None

        try:
            tool_callable = self._resolver(request.server, request.tool_name)
            payload = await asyncio.wait_for(
                self._execute_tool(tool_callable, request.arguments),
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            status = "error"
            error_message = str(exc)
            logger.warning(
                "MCP gateway call failed (%s.%s): %s",
                request.server,
                request.tool_name,
                exc,
            )

        latency_ms = round((perf_counter() - started) * 1000, 2)

        result = MCPToolCallResult(
            run_id=request.run_id,
            agent_name=request.agent_name,
            step_name=request.step_name,
            server=request.server,
            tool_name=request.tool_name,
            arguments=request.arguments,
            result=payload,
            status=status,
            latency_ms=latency_ms,
            error_message=error_message,
        )
        record_tool_trace(MCPToolTrace(**result.model_dump()))
        return result


mcp_gateway = MCPClientGateway()
