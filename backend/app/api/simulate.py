"""Scenario simulation endpoint."""

from fastapi import APIRouter, HTTPException

from app.models.schemas import SimulationRequest, SimulationResult
from app.mcp_client.gateway import mcp_gateway
from app.services.finance_engine import FinanceEngine
from app.services.storage_service import get_product as db_get_product

router = APIRouter()


@router.post("/simulate/{run_id}/{sku}", response_model=SimulationResult)
async def simulate(run_id: str, sku: str, req: SimulationRequest):
    """Run a what-if scenario for a SKU."""
    engine = FinanceEngine.get_cached(run_id)
    product = engine.get_product(sku) if engine else None
    if product is None:
        product = db_get_product(run_id, sku)
    if product is None:
        raise HTTPException(status_code=404, detail=f"SKU not found: {sku}")

    gateway_result = await mcp_gateway.call_tool(
        server="finance-mcp",
        tool_name="simulate_scenario",
        arguments={
            "run_id": run_id,
            "sku": sku,
            "new_price": req.new_price,
            "ad_budget_change_pct": req.ad_budget_change_pct,
            "expected_return_rate_change_pct": req.expected_return_rate_change_pct,
            "expected_demand_change_pct": req.expected_demand_change_pct,
        },
        run_id=run_id,
        agent_name="Simulation Agent",
        step_name="Scenario Simulation",
    )

    if gateway_result.status != "success":
        detail = gateway_result.error_message or "Simulation tool call failed."
        lowered = detail.lower()
        if "not found" in lowered:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    payload = gateway_result.result
    if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
        raise HTTPException(status_code=500, detail="Invalid simulation payload from MCP gateway.")

    return SimulationResult.model_validate(payload["result"])

