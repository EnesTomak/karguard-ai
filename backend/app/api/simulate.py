"""Scenario simulation endpoint."""

from fastapi import APIRouter, HTTPException

from app.models.schemas import SimulationRequest, SimulationResult
from app.services.simulation_service import run_simulation
from app.services.finance_engine import FinanceEngine

router = APIRouter()


@router.post("/simulate/{run_id}/{sku}", response_model=SimulationResult)
async def simulate(run_id: str, sku: str, req: SimulationRequest):
    """Run a what-if price/ad/return scenario for a SKU."""
    engine = FinanceEngine.get_cached(run_id)
    if engine is None:
        raise HTTPException(status_code=404, detail="Analiz bulunamadı.")

    product = engine.get_product(sku)
    if product is None:
        raise HTTPException(status_code=404, detail=f"SKU {sku} bulunamadı.")

    return run_simulation(product, req)
