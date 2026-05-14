"""Dashboard endpoint - KPIs and product overview."""

from fastapi import APIRouter, HTTPException

from app.models.schemas import DashboardResponse
from app.services.finance_engine import FinanceEngine
from app.services.storage_service import get_dashboard as db_get_dashboard

router = APIRouter()


@router.get("/dashboard/{run_id}", response_model=DashboardResponse)
async def get_dashboard(run_id: str):
    """Return dashboard KPIs and SKU profitability table."""
    engine = FinanceEngine.get_cached(run_id)
    if engine is not None:
        return engine.get_dashboard_response(run_id)

    snapshot = db_get_dashboard(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Analysis not found for this run_id.")
    return snapshot

