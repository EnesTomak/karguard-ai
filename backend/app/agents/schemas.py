"""Shared schemas for future agent modules."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AgentExecutionContext(BaseModel):
    run_id: str
    agent_name: str
    step_name: str


class AgentExecutionResult(BaseModel):
    status: Literal["success", "error"] = "success"
    message: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)
