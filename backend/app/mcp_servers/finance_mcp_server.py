"""Finance MCP server.

Exposes deterministic finance capabilities as MCP tools:
- calculate_sku_profitability
- detect_loss_makers
- simulate_scenario
- forecast_cashflow_14d
- calculate_risk_score
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.config import settings
from app.models.schemas import SimulationRequest
from app.services.finance_engine import FinanceEngine
from app.services.simulation_service import run_simulation

mcp = FastMCP("finance-mcp")


def _ensure_engine(run_id: str) -> FinanceEngine:
    """Load engine from cache or build it from upload directory."""
    engine = FinanceEngine.get_cached(run_id)
    if engine is not None:
        return engine

    run_dir = settings.UPLOAD_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run not found: {run_id}")

    engine = FinanceEngine.from_directory(run_dir)
    engine.cache(run_id)
    return engine


def _product_to_dict(product: Any) -> dict[str, Any]:
    """Convert pydantic model to plain dict."""
    return product.model_dump()


@mcp.tool()
def calculate_sku_profitability(
    run_id: str,
    sku: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Return SKU profitability metrics for one SKU or a list sorted by risk."""
    engine = _ensure_engine(run_id)

    if sku:
        product = engine.get_product(sku)
        if product is None:
            raise ValueError(f"SKU not found: {sku}")
        return {
            "run_id": run_id,
            "count": 1,
            "items": [_product_to_dict(product)],
        }

    items = engine.get_all_products()[: max(1, limit)]
    return {
        "run_id": run_id,
        "count": len(items),
        "items": [_product_to_dict(p) for p in items],
    }


@mcp.tool()
def detect_loss_makers(run_id: str, limit: int = 50) -> dict[str, Any]:
    """Return loss-making SKUs (net_profit < 0), sorted by worst loss first."""
    engine = _ensure_engine(run_id)
    items = sorted(engine.get_loss_makers(), key=lambda p: p.net_profit)[: max(1, limit)]

    return {
        "run_id": run_id,
        "count": len(items),
        "items": [_product_to_dict(p) for p in items],
    }


@mcp.tool()
def simulate_scenario(
    run_id: str,
    sku: str,
    new_price: float | None = None,
    ad_budget_change_pct: float | None = None,
    expected_return_rate_change_pct: float | None = None,
    expected_demand_change_pct: float | None = None,
) -> dict[str, Any]:
    """Run deterministic what-if simulation for a SKU."""
    engine = _ensure_engine(run_id)
    product = engine.get_product(sku)
    if product is None:
        raise ValueError(f"SKU not found: {sku}")

    req = SimulationRequest(
        new_price=new_price,
        ad_budget_change_pct=ad_budget_change_pct,
        expected_return_rate_change_pct=expected_return_rate_change_pct,
        expected_demand_change_pct=expected_demand_change_pct,
    )
    result = run_simulation(product, req)
    return {
        "run_id": run_id,
        "sku": sku,
        "result": result.model_dump(),
    }


@mcp.tool()
def forecast_cashflow_14d(run_id: str) -> dict[str, Any]:
    """Return 14-day cashflow forecast from deterministic engine."""
    engine = _ensure_engine(run_id)
    return {
        "run_id": run_id,
        "cashflow_14d": engine.kpis.cashflow_14d,
    }


@mcp.tool()
def calculate_risk_score(run_id: str, sku: str) -> dict[str, Any]:
    """Return risk score and level for a specific SKU."""
    engine = _ensure_engine(run_id)
    product = engine.get_product(sku)
    if product is None:
        raise ValueError(f"SKU not found: {sku}")

    return {
        "run_id": run_id,
        "sku": sku,
        "risk_score": product.risk_score,
        "risk_level": product.risk_level.value,
        "net_profit": product.net_profit,
        "platform_fee": product.platform_fee,
        "transaction_fee": product.transaction_fee,
        "return_rate": product.return_rate,
        "ad_to_revenue_ratio": product.ad_to_revenue_ratio,
    }


if __name__ == "__main__":
    mcp.run()

