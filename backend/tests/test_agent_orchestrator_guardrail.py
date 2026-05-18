from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from app.config import settings
from app.models.schemas import AnalysisRunResponse, AnalysisStatus, RootCauseAnalysis
from app.services.agent_orchestrator import run_pipeline
from app.services.insight_agent import AgenticLossMakerResult
from app.services.storage_service import get_dashboard, upsert_analysis_run


def _write_csv(path: Path, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def _seed_run_files(run_id: str) -> Path:
    run_dir = settings.UPLOAD_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_csv(
        run_dir / "orders.csv",
        [
            {
                "order_id": "o1",
                "sku": "SKU-LOSS",
                "quantity": 1,
                "unit_price": 100,
                "commission_rate": 0.10,
                "cargo_cost": 10,
            },
            {
                "order_id": "o2",
                "sku": "SKU-GOOD",
                "quantity": 1,
                "unit_price": 200,
                "commission_rate": 0.05,
                "cargo_cost": 5,
            },
        ],
    )
    _write_csv(
        run_dir / "products.csv",
        [
            {"sku": "SKU-LOSS", "name": "Loss Product", "category": "Cat", "unit_cost": 130},
            {"sku": "SKU-GOOD", "name": "Good Product", "category": "Cat", "unit_cost": 50},
        ],
    )
    _write_csv(
        run_dir / "returns.csv",
        [
            {"return_id": "r1", "sku": "SKU-LOSS", "return_reason": "size", "refund_amount": 100, "return_shipping_cost": 10},
        ],
    )
    _write_csv(
        run_dir / "ads.csv",
        [
            {"sku": "SKU-LOSS", "spend": 40},
            {"sku": "SKU-GOOD", "spend": 10},
        ],
    )
    _write_csv(
        run_dir / "reviews.csv",
        [
            {"sku": "SKU-LOSS", "rating": 2, "comment": "Bekledigim kalite degil"},
            {"sku": "SKU-GOOD", "rating": 5, "comment": "Harika"},
        ],
    )
    return run_dir


@pytest.mark.asyncio
async def test_guardrail_fallback_message_when_no_verified_agentic_sku(monkeypatch):
    run_id = "guardrail-fallback-run"
    run_dir = _seed_run_files(run_id)

    upsert_analysis_run(
        AnalysisRunResponse(
            run_id=run_id,
            status=AnalysisStatus.RUNNING,
            created_at=datetime.now().isoformat(),
            agent_steps=[],
        )
    )

    async def fake_agentic_detect(_: str) -> AgenticLossMakerResult:
        # Agent returns a SKU that is not a deterministic loss maker.
        return AgenticLossMakerResult(
            skus=["SKU-NOT-REAL-LOSS"],
            used_fallback=False,
            error_message=None,
        )

    def fake_index_all(_: Path) -> dict[str, int | bool]:
        return {"skipped": True, "reviews": 0, "products": 0, "policies": 0}

    async def fake_analyze_root_cause(product, _run_dir: Path) -> RootCauseAnalysis:
        return RootCauseAnalysis(
            sku=product.sku,
            product_name=product.product_name,
            main_cause="fallback",
            explanation="fallback",
        )

    async def fake_generate_action_plan(_product, _root_cause) -> list:
        return []

    monkeypatch.setattr("app.services.insight_agent.agentic_detect_loss_makers", fake_agentic_detect)
    monkeypatch.setattr("app.services.qdrant_service.index_all", fake_index_all)
    monkeypatch.setattr("app.services.insight_agent.analyze_root_cause", fake_analyze_root_cause)
    monkeypatch.setattr("app.services.insight_agent.generate_action_plan", fake_generate_action_plan)

    result = await run_pipeline(run_id=run_id, run_dir=run_dir)
    loss_step = next(step for step in result.agent_steps if step.step_name == "Loss Maker Agent")
    assert "guardrail doğrulamasından geçen SKU bulunamadı" in loss_step.message
    assert "deterministic fallback kullanıldı" in loss_step.message

    dashboard = get_dashboard(run_id)
    assert dashboard is not None
    assert {item.sku for item in dashboard.loss_makers} == {"SKU-LOSS"}

