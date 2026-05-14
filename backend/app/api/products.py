"""Product detail & intelligence endpoint."""

from fastapi import APIRouter, HTTPException

from app.models.schemas import SKUProfitability, ProductIntelligence, RootCauseAnalysis
from app.services.finance_engine import FinanceEngine

router = APIRouter()


@router.get("/products/{run_id}", response_model=list[SKUProfitability])
async def get_products(run_id: str):
    """Return SKU-level profitability table."""
    engine = FinanceEngine.get_cached(run_id)
    if engine is None:
        raise HTTPException(status_code=404, detail="Analiz bulunamadı.")
    return engine.get_all_products()


@router.get("/products/{run_id}/{sku}", response_model=ProductIntelligence)
async def get_product_detail(run_id: str, sku: str):
    """Return full intelligence for a single SKU (profitability + root cause + actions)."""
    engine = FinanceEngine.get_cached(run_id)
    if engine is None:
        raise HTTPException(status_code=404, detail="Analiz bulunamadı.")

    product = engine.get_product(sku)
    if product is None:
        raise HTTPException(status_code=404, detail=f"SKU {sku} bulunamadı.")

    # Get root cause from cache
    from app.services.agent_orchestrator import get_root_cause
    root_cause = get_root_cause(run_id, sku)
    if root_cause is None:
        root_cause = RootCauseAnalysis(
            sku=sku,
            product_name=product.product_name,
        )

    # Get actions for this SKU
    from app.api.actions import get_actions_for_sku
    actions = get_actions_for_sku(run_id, sku)

    return ProductIntelligence(
        profitability=product,
        root_cause=root_cause,
        actions=actions,
    )
