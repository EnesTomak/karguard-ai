"""Scenario simulation endpoint."""

from fastapi import APIRouter, HTTPException

from app.models.schemas import SimulationRequest, SimulationResult
from app.services.finance_engine import FinanceEngine
from app.services.simulation_service import run_simulation
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

    return run_simulation(product, req)

