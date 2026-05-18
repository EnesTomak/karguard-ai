"""Audit trace storage for MCP tool calls."""

from __future__ import annotations

import logging
from threading import Lock

from app.mcp_client.schemas import MCPToolTrace
from app.services.storage_service import insert_mcp_tool_trace, list_mcp_tool_trace_json

logger = logging.getLogger(__name__)

_TRACE_LOCK = Lock()
_IN_MEMORY_TRACES: list[MCPToolTrace] = []


def clear_tool_traces() -> None:
    """Clear in-memory traces. Useful for tests."""
    with _TRACE_LOCK:
        _IN_MEMORY_TRACES.clear()


def record_tool_trace(trace: MCPToolTrace) -> None:
    """Record a tool trace in memory and SQLite."""
    with _TRACE_LOCK:
        _IN_MEMORY_TRACES.append(trace)

    try:
        insert_mcp_tool_trace(
            trace_id=trace.trace_id,
            run_id=trace.run_id,
            trace_json=trace.model_dump_json(),
            created_at=trace.created_at,
        )
    except Exception as exc:
        logger.warning("MCP trace SQLite persist failed (%s): %s", trace.trace_id, exc)


def get_tool_traces(run_id: str) -> list[MCPToolTrace]:
    """Read traces by run_id from memory + SQLite without duplicates."""
    traces_by_id: dict[str, MCPToolTrace] = {}

    for persisted_json in list_mcp_tool_trace_json(run_id):
        try:
            persisted = MCPToolTrace.model_validate_json(persisted_json)
        except Exception as exc:
            logger.warning("Skipping invalid persisted MCP trace for run_id=%s: %s", run_id, exc)
            continue
        traces_by_id[persisted.trace_id] = persisted

    with _TRACE_LOCK:
        for trace in _IN_MEMORY_TRACES:
            if trace.run_id == run_id:
                traces_by_id[trace.trace_id] = trace

    return sorted(traces_by_id.values(), key=lambda item: item.created_at)
