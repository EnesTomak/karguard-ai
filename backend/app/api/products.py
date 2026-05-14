"""Product detail and intelligence endpoints."""

from fastapi import APIRouter, HTTPException

from app.models.schemas import ProductIntelligence, RootCauseAnalysis, SKUProfitability
from app.services.finance_engine import FinanceEngine
from app.services.storage_service import (
    get_product as db_get_product,
    get_products as db_get_products,
    get_root_cause as db_get_root_cause,
    list_actions_for_sku as db_list_actions_for_sku,
)

router = APIRouter()


@router.get("/products/{run_id}", response_model=list[SKUProfitability])
async def get_products(run_id: str):
    """Return SKU-level profitability table."""
    engine = FinanceEngine.get_cached(run_id)
    if engine is not None:
        return engine.get_all_products()

    items = db_get_products(run_id)
    if not items:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return items


@router.get("/products/{run_id}/{sku}", response_model=ProductIntelligence)
async def get_product_detail(run_id: str, sku: str):
    """Return full intelligence for a single SKU."""
    engine = FinanceEngine.get_cached(run_id)
    if engine is not None:
        product = engine.get_product(sku)
    else:
        product = db_get_product(run_id, sku)

    if product is None:
        raise HTTPException(status_code=404, detail=f"SKU not found: {sku}")

    from app.services.agent_orchestrator import get_root_cause

    root_cause = get_root_cause(run_id, sku)
    if root_cause is None:
        root_cause = db_get_root_cause(run_id, sku)
    if root_cause is None:
        root_cause = RootCauseAnalysis(
            sku=sku,
            product_name=product.product_name,
        )

    from app.api.actions import get_actions_for_sku

    actions = get_actions_for_sku(run_id, sku)
    if not actions:
        actions = db_list_actions_for_sku(run_id, sku)

    return ProductIntelligence(
        profitability=product,
        root_cause=root_cause,
        actions=actions,
    )

