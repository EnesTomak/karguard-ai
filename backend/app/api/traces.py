"""MCP tool trace endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.mcp_client.audit import get_tool_traces
from app.mcp_client.schemas import MCPToolTrace

router = APIRouter()


@router.get("/traces/{run_id}", response_model=list[MCPToolTrace])
async def list_traces(run_id: str):
    """Return MCP tool traces for a run."""
    return get_tool_traces(run_id)

