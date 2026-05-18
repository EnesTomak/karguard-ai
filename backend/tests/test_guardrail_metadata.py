from __future__ import annotations

from datetime import datetime

import pytest

from app.mcp_client.audit import record_tool_trace
from app.mcp_client.schemas import MCPToolTrace
from app.models.schemas import (
    AnalysisRunResponse,
    AnalysisStatus,
    EvidenceItem,
    RootCauseAnalysis,
)
from app.services.guardrail_service import (
    build_guardrail_report,
    verify_evidence_refs,
    verify_loss_maker_skus,
)
from app.services.storage_service import upsert_analysis_run, upsert_guardrail_report


def _seed_run(run_id: str) -> None:
    upsert_analysis_run(
        AnalysisRunResponse(
            run_id=run_id,
            status=AnalysisStatus.COMPLETED,
            created_at=datetime.now().isoformat(),
            agent_steps=[],
        )
    )


def test_verify_loss_maker_skus_rejects_invalid_agent_sku():
    check = verify_loss_maker_skus(["SKU-UNKNOWN"], {"SKU-LOSS"})
    assert check["status"] == "failed"
    assert "SKU-UNKNOWN" in check["metadata"]["invalid_skus"]
    assert check["metadata"]["verified_skus"] == []


def test_guardrail_report_marks_degraded_when_invalid_sku():
    loss_check = verify_loss_maker_skus(["SKU-LOSS", "SKU-INVALID"], {"SKU-LOSS"})
    report = build_guardrail_report(loss_maker_check=loss_check)
    assert loss_check["status"] == "degraded"
    assert report.status == "degraded"


def test_guardrail_report_passes_with_valid_loss_maker_sku():
    loss_check = verify_loss_maker_skus(["SKU-LOSS"], {"SKU-LOSS"})
    report = build_guardrail_report(loss_maker_check=loss_check)
    assert loss_check["status"] == "passed"
    assert report.status == "passed"


@pytest.mark.asyncio
async def test_guardrail_endpoint_returns_report(client):
    run_id = "guardrail-endpoint-run"
    _seed_run(run_id)

    report = build_guardrail_report(
        loss_maker_check=verify_loss_maker_skus(["SKU-LOSS"], {"SKU-LOSS"}),
        evidence_check={
            "name": "evidence_reference_validation",
            "status": "passed",
            "message": "ok",
            "metadata": {"evidence_refs_valid": True},
        },
    )
    upsert_guardrail_report(run_id, report)

    response = await client.get(f"/api/guardrails/{run_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["verified_by"] == "deterministic_finance_engine"
    assert isinstance(payload["checks"], list)
    assert any(check["name"] == "loss_maker_sku_validation" for check in payload["checks"])


def test_evidence_refs_valid_when_evidence_exists():
    root_cause = RootCauseAnalysis(
        sku="SKU-1",
        product_name="Demo Product",
        main_cause_supporting_refs=["rev-1"],
        evidence=[
            EvidenceItem(
                source="rag_review",
                text="Kumas ince geldi",
                reference_id="rev-1",
                relevance_score=0.91,
            )
        ],
    )

    check = verify_evidence_refs(root_cause=root_cause, evidence_items=root_cause.evidence)
    assert check["status"] == "passed"
    assert check["metadata"]["evidence_refs_valid"] is True


@pytest.mark.asyncio
async def test_simulation_trace_can_be_linked_to_guardrail_metadata(client):
    run_id = "guardrail-simulation-run"
    _seed_run(run_id)
    upsert_guardrail_report(
        run_id,
        build_guardrail_report(
            loss_maker_check={
                "name": "loss_maker_sku_validation",
                "status": "passed",
                "message": "ok",
                "metadata": {},
            }
        ),
    )

    record_tool_trace(
        MCPToolTrace(
            run_id=run_id,
            agent_name="Simulation Agent",
            step_name="Scenario Simulation",
            server="finance-mcp",
            tool_name="simulate_scenario",
            arguments={"run_id": run_id, "sku": "SKU-1"},
            result={
                "run_id": run_id,
                "sku": "SKU-1",
                "result": {
                    "scenario_label": "Test",
                    "current_profit": -120.0,
                    "simulated_profit": 20.0,
                    "profit_delta": 140.0,
                    "new_margin": 3.1,
                    "assumptions": [],
                },
            },
            status="success",
            latency_ms=5.5,
            error_message=None,
        )
    )

    response = await client.get(f"/api/guardrails/{run_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["simulation_verified"] is True
    assert any(check["name"] == "simulation_result_validation" for check in payload["checks"])
    assert payload["tool_trace_ids"]
