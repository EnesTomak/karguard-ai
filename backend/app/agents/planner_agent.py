"""Planner agent compatibility layer."""

from __future__ import annotations

from app.models.schemas import ActionCard, RootCauseAnalysis, SKUProfitability
from app.services.insight_agent import generate_action_plan


async def plan_actions(product: SKUProfitability, root_cause: RootCauseAnalysis) -> list[ActionCard]:
    """Delegate action planning to the current service implementation."""
    return await generate_action_plan(product, root_cause)
