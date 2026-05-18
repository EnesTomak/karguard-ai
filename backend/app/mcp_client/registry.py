"""Tool registry for MCP gateway routing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.mcp_servers import finance_mcp_server

MCPToolCallable = Callable[..., Any]


_TOOL_REGISTRY: dict[str, dict[str, MCPToolCallable]] = {
    "finance-mcp": {
        "calculate_sku_profitability": finance_mcp_server.calculate_sku_profitability_tool,
        "detect_loss_makers": finance_mcp_server.detect_loss_makers_tool,
        "detect_loss_maker_skus": finance_mcp_server.detect_loss_maker_skus_tool,
        "simulate_scenario": finance_mcp_server.simulate_scenario_tool,
        "forecast_cashflow_14d": finance_mcp_server.forecast_cashflow_14d_tool,
        "calculate_risk_score": finance_mcp_server.calculate_risk_score_tool,
    }
}


def get_tool_callable(server: str, tool_name: str) -> MCPToolCallable:
    """Resolve tool callable from registry or raise ValueError."""
    server_tools = _TOOL_REGISTRY.get(server)
    if server_tools is None:
        raise ValueError(f"Unknown MCP server: {server}")

    tool = server_tools.get(tool_name)
    if tool is None:
        raise ValueError(f"Unknown tool for server '{server}': {tool_name}")

    return tool


def list_tools(server: str) -> list[str]:
    """List registered tools for a server."""
    server_tools = _TOOL_REGISTRY.get(server)
    if server_tools is None:
        return []
    return sorted(server_tools.keys())

