"""Guardrail reporting endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.mcp_client.audit import get_tool_traces
from app.models.schemas import GuardrailReport
from app.services.guardrail_service import build_guardrail_report, verify_simulation_result
from app.services.storage_service import get_analysis_run, get_guardrail_report

router = APIRouter()


def _latest_successful_simulation_payload(run_id: str) -> dict | None:
    traces = get_tool_traces(run_id)
    for trace in reversed(traces):
        if trace.server == "finance-mcp" and trace.tool_name == "simulate_scenario" and trace.status == "success":
            return trace.result if isinstance(trace.result, dict) else None
    return None


@router.get("/guardrails/{run_id}", response_model=GuardrailReport)
async def get_guardrails(run_id: str):
    """Return guardrail metadata for a run."""
    if get_analysis_run(run_id) is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    persisted = get_guardrail_report(run_id)
    if persisted is None:
        persisted = build_guardrail_report()

    simulation_check = verify_simulation_result(_latest_successful_simulation_payload(run_id))
    merged = build_guardrail_report(
        loss_maker_check=next((check.model_dump() for check in persisted.checks if check.name == "loss_maker_sku_validation"), None),
        evidence_check=next((check.model_dump() for check in persisted.checks if check.name == "evidence_reference_validation"), None),
        simulation_check=simulation_check,
        verified_by=persisted.verified_by,
        tool_trace_ids=[trace.trace_id for trace in get_tool_traces(run_id)],
    )
    return merged
