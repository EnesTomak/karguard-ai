"""Trace helpers for observability views."""

from __future__ import annotations

from app.mcp_client.audit import get_tool_traces
from app.mcp_client.schemas import MCPToolTrace


def list_mcp_traces_for_run(run_id: str) -> list[MCPToolTrace]:
    """Return MCP traces for a run."""
    return get_tool_traces(run_id)
