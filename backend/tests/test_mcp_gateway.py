from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.config import settings
from app.mcp_client.audit import get_tool_traces, record_tool_trace
from app.mcp_client.gateway import mcp_gateway
from app.mcp_client.schemas import MCPToolCallResult, MCPToolTrace
from app.services.finance_engine import FinanceEngine
from app.services.insight_agent import agentic_detect_loss_makers


def _write_csv(path: Path, rows: list[dict]):
    pd.DataFrame(rows).to_csv(path, index=False)


def _seed_finance_run(run_id: str) -> None:
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
        run_dir / "ads.csv",
        [
            {"sku": "SKU-LOSS", "spend": 40},
            {"sku": "SKU-GOOD", "spend": 10},
        ],
    )
    _write_csv(
        run_dir / "returns.csv",
        [
            {"return_id": "r1", "sku": "SKU-LOSS", "refund_amount": 100, "return_shipping_cost": 10},
        ],
    )
    _write_csv(
        run_dir / "reviews.csv",
        [
            {"sku": "SKU-LOSS", "rating": 2, "comment": "Bekledigim kalite degil"},
            {"sku": "SKU-GOOD", "rating": 5, "comment": "Harika"},
        ],
    )

    engine = FinanceEngine.from_directory(run_dir)
    engine.cache(run_id)


@pytest.mark.asyncio
async def test_mcp_gateway_call_detect_loss_maker_skus():
    run_id = "mcp-gateway-run"
    _seed_finance_run(run_id)

    result = await mcp_gateway.call_tool(
        server="finance-mcp",
        tool_name="detect_loss_maker_skus",
        arguments={"run_id": run_id, "limit": 10},
        run_id=run_id,
        agent_name="test-agent",
        step_name="test-step",
    )

    assert result.status == "success"
    assert result.server == "finance-mcp"
    assert result.tool_name == "detect_loss_maker_skus"
    assert isinstance(result.result, dict)
    assert result.result["run_id"] == run_id
    assert "SKU-LOSS" in result.result["skus"]
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_mcp_gateway_records_trace():
    run_id = "mcp-trace-run"
    _seed_finance_run(run_id)

    _ = await mcp_gateway.call_tool(
        server="finance-mcp",
        tool_name="detect_loss_maker_skus",
        arguments={"run_id": run_id, "limit": 10},
        run_id=run_id,
        agent_name="test-agent",
        step_name="trace-step",
    )

    traces = get_tool_traces(run_id)
    assert traces
    latest = traces[-1]
    assert latest.server == "finance-mcp"
    assert latest.tool_name == "detect_loss_maker_skus"
    assert latest.status == "success"
    assert latest.latency_ms >= 0


@pytest.mark.asyncio
async def test_agentic_detect_loss_makers_uses_gateway(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_call_tool(
        server: str,
        tool_name: str,
        arguments: dict[str, object],
        run_id: str | None = None,
        agent_name: str | None = None,
        step_name: str | None = None,
    ) -> MCPToolCallResult:
        captured["server"] = server
        captured["tool_name"] = tool_name
        captured["arguments"] = arguments
        captured["run_id"] = run_id
        captured["agent_name"] = agent_name
        captured["step_name"] = step_name
        return MCPToolCallResult(
            run_id=run_id,
            agent_name=agent_name,
            step_name=step_name,
            server=server,
            tool_name=tool_name,
            arguments=arguments,
            result={"run_id": arguments["run_id"], "skus": ["SKU-LOSS"], "count": 1},
            status="success",
            latency_ms=4.2,
            error_message=None,
        )

    async def fake_generate_structured_with_tools(**kwargs):
        assert kwargs["force_any_function"] is True
        assert kwargs["allowed_function_names"] == ["detect_loss_maker_skus_gateway_tool"]
        tools = kwargs["tools"]
        tool_result = await tools[0](run_id="run-xyz", limit=5)
        return {"skus": tool_result["skus"]}

    monkeypatch.setattr("app.services.insight_agent.generate_structured_with_tools", fake_generate_structured_with_tools)
    monkeypatch.setattr("app.services.insight_agent.mcp_gateway.call_tool", fake_call_tool)

    result = await agentic_detect_loss_makers("run-xyz")
    assert result.skus == ["SKU-LOSS"]
    assert result.used_fallback is False
    assert captured["server"] == "finance-mcp"
    assert captured["tool_name"] == "detect_loss_maker_skus"
    assert captured["run_id"] == "run-xyz"


@pytest.mark.asyncio
async def test_trace_endpoint_returns_records(client):
    run_id = "trace-api-run"
    record_tool_trace(
        MCPToolTrace(
            run_id=run_id,
            agent_name="Loss Maker Agent",
            step_name="Loss Maker Detection",
            server="finance-mcp",
            tool_name="detect_loss_maker_skus",
            arguments={"run_id": run_id, "limit": 10},
            result={"run_id": run_id, "skus": ["SKU-LOSS"], "count": 1},
            status="success",
            latency_ms=7.7,
            error_message=None,
        )
    )

    response = await client.get(f"/api/traces/{run_id}")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert payload
    assert payload[0]["run_id"] == run_id
    assert payload[0]["server"] == "finance-mcp"
    assert payload[0]["tool_name"] == "detect_loss_maker_skus"
