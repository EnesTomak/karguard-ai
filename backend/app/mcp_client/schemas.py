"""Schemas for MCP tool calls and traces."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MCPToolCallRequest(BaseModel):
    """Normalized request contract for gateway tool calls."""

    run_id: str | None = None
    agent_name: str | None = None
    step_name: str | None = None
    server: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPToolCallResult(BaseModel):
    """Gateway result contract returned to callers."""

    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    run_id: str | None = None
    agent_name: str | None = None
    step_name: str | None = None
    server: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any | None = None
    status: Literal["success", "error"]
    latency_ms: float = 0.0
    error_message: str | None = None
    created_at: str = Field(default_factory=_utc_now_iso)


class MCPToolTrace(MCPToolCallResult):
    """Persisted trace model for MCP tool calls."""

