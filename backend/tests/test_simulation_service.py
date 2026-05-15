from __future__ import annotations

import pytest

from app.models.schemas import RiskLevel, SKUProfitability, SimulationRequest
from app.services.simulation_service import run_simulation


def test_run_simulation_returns_expected_profit_delta():
    product = SKUProfitability(
        sku="SKU-1",
        product_name="Demo Product",
        risk_level=RiskLevel.MEDIUM,
        quantity_sold=10,
        gross_revenue=1000,
        cogs=500,
        commission_cost=100,
        shipping_cost=50,
        ad_spend=100,
        return_count=2,
        return_rate=20,
        refund_amount=200,
        return_shipping_cost=20,
        net_profit=30,
    )
    req = SimulationRequest(
        new_price=110,
        ad_budget_change_pct=-20,
        expected_return_rate_change_pct=-50,
        expected_demand_change_pct=10,
    )

    result = run_simulation(product, req)

    assert result.scenario_label
    assert result.current_profit == 30
    assert result.simulated_profit == pytest.approx(294.0, abs=0.01)
    assert result.profit_delta == pytest.approx(264.0, abs=0.01)
    assert result.new_margin == pytest.approx(24.3, abs=0.01)
    assert len(result.assumptions) == 5

