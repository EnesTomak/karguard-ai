"""Guardrail agent compatibility layer."""

from __future__ import annotations

from typing import Any

from app.models.schemas import GuardrailReport
from app.services.guardrail_service import (
    build_guardrail_report,
    verify_evidence_refs,
    verify_loss_maker_skus,
    verify_simulation_result,
)


def run_guardrails(
    *,
    agent_skus: list[str],
    deterministic_skus: set[str],
    root_cause: Any = None,
    evidence_items: Any = None,
    simulation_result: Any = None,
    tool_trace_ids: list[str] | None = None,
) -> GuardrailReport:
    """Build a composed guardrail report from available validation inputs."""
    return build_guardrail_report(
        loss_maker_check=verify_loss_maker_skus(agent_skus, deterministic_skus),
        evidence_check=verify_evidence_refs(root_cause, evidence_items) if root_cause is not None else None,
        simulation_check=verify_simulation_result(simulation_result) if simulation_result is not None else None,
        tool_trace_ids=tool_trace_ids or [],
    )
