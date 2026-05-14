"""Dashboard endpoint — KPIs and product overview."""

from fastapi import APIRouter, HTTPException

from app.models.schemas import DashboardResponse
from app.services.finance_engine import FinanceEngine

router = APIRouter()


@router.get("/dashboard/{run_id}", response_model=DashboardResponse)
async def get_dashboard(run_id: str):
    """Return dashboard KPIs and SKU profitability table."""
    engine = FinanceEngine.get_cached(run_id)
    if engine is None:
        raise HTTPException(status_code=404, detail="Bu run_id için analiz bulunamadı. Önce /api/analyze çağırın.")

    return engine.get_dashboard_response(run_id)
