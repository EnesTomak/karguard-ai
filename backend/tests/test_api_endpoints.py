from __future__ import annotations

from datetime import datetime

import pytest

from app.api.actions import register_actions
from app.models.schemas import (
    ActionCard,
    ActionStatus,
    AnalysisRunResponse,
    AnalysisStatus,
    RiskLevel,
    SKUProfitability,
)
from app.services.finance_engine import FinanceEngine
from app.services.storage_service import upsert_analysis_run


def _seed_run(run_id: str) -> None:
    upsert_analysis_run(
        AnalysisRunResponse(
            run_id=run_id,
            status=AnalysisStatus.COMPLETED,
            created_at=datetime.now().isoformat(),
            agent_steps=[],
        )
    )


@pytest.mark.asyncio
async def test_root_endpoint(client):
    response = await client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"


@pytest.mark.asyncio
async def test_dashboard_not_found_returns_structured_error(client):
    response = await client.get("/api/dashboard/missing-run")
    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "http_error"
    assert payload["detail"] == "Analysis not found for this run_id."
    assert payload["path"] == "/api/dashboard/missing-run"
    assert "request_id" in payload


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_extension(client):
    files = [
        ("files", ("malware.exe", b"noop", "application/octet-stream")),
    ]
    response = await client.post("/api/upload", files=files)
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "http_error"
    assert "Desteklenmeyen dosya t" in payload["detail"]


@pytest.mark.asyncio
async def test_simulate_endpoint_uses_cached_product(client):
    run_id = "run-123"
    sku = "SKU-1"

    engine = FinanceEngine()
    engine.profitability[sku] = SKUProfitability(
        sku=sku,
        product_name="Demo Product",
        risk_level=RiskLevel.LOW,
        quantity_sold=10,
        gross_revenue=1000,
        cogs=500,
        commission_cost=100,
        shipping_cost=50,
        ad_spend=100,
        return_count=1,
        return_rate=10,
        refund_amount=100,
        return_shipping_cost=10,
        net_profit=140,
    )
    engine.cache(run_id)

    response = await client.post(
        f"/api/simulate/{run_id}/{sku}",
        json={
            "new_price": 120,
            "expected_demand_change_pct": 0,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario_label"]
    assert isinstance(payload["simulated_profit"], (int, float))


@pytest.mark.asyncio
async def test_edit_action_updates_pending_card(client):
    run_id = "run-actions"
    _seed_run(run_id)
    card = ActionCard(
        action_id="act-1234",
        sku="SKU-1",
        action_type="price_change",
        title="Old title",
        reason="Old reason",
        expected_impact="Old impact",
        risk_level=RiskLevel.MEDIUM,
        status=ActionStatus.PENDING,
    )
    register_actions([card], run_id)

    response = await client.patch(
        "/api/actions/act-1234/edit",
        json={
            "title": "New title",
            "reason": "New reason",
            "risk_level": "low",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "New title"
    assert payload["reason"] == "New reason"
    assert payload["risk_level"] == "low"


@pytest.mark.asyncio
async def test_edit_action_rejects_non_pending_card(client):
    run_id = "run-actions-2"
    _seed_run(run_id)
    card = ActionCard(
        action_id="act-5678",
        sku="SKU-1",
        action_type="ad_budget",
        title="Approved action",
        reason="Approved",
        expected_impact="Impact",
        risk_level=RiskLevel.LOW,
        status=ActionStatus.APPROVED,
    )
    register_actions([card], run_id)

    response = await client.patch(
        "/api/actions/act-5678/edit",
        json={"title": "Should fail"},
    )
    assert response.status_code == 409
    payload = response.json()
    assert payload["detail"] == "Only pending actions can be edited."
