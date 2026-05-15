from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.services.finance_engine import FinanceEngine


def _write_csv(path: Path, rows: list[dict]):
    pd.DataFrame(rows).to_csv(path, index=False)


def test_finance_engine_calculates_profitability_and_kpis(tmp_path):
    run_dir = tmp_path / "run001"
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_csv(
        run_dir / "orders.csv",
        [
            {"order_id": "o1", "sku": "SKU-A", "quantity": 2, "unit_price": 100, "commission_rate": 0.10, "cargo_cost": 5},
            {"order_id": "o2", "sku": "SKU-A", "quantity": 1, "unit_price": 100, "commission_rate": 0.10, "cargo_cost": 5},
            {"order_id": "o3", "sku": "SKU-B", "quantity": 1, "unit_price": 50, "commission_rate": 0.10, "cargo_cost": 4},
        ],
    )
    _write_csv(
        run_dir / "returns.csv",
        [
            {"return_id": "r1", "sku": "SKU-A", "refund_amount": 100, "return_shipping_cost": 10},
        ],
    )
    _write_csv(
        run_dir / "products.csv",
        [
            {"sku": "SKU-A", "name": "A Product", "category": "Cat-A", "unit_cost": 70},
            {"sku": "SKU-B", "name": "B Product", "category": "Cat-B", "unit_cost": 20},
        ],
    )
    _write_csv(
        run_dir / "ads.csv",
        [
            {"sku": "SKU-A", "spend": 60},
            {"sku": "SKU-B", "spend": 10},
        ],
    )

    engine = FinanceEngine.from_directory(run_dir)
    products = engine.get_all_products()
    assert len(products) == 2

    sku_a = engine.get_product("SKU-A")
    sku_b = engine.get_product("SKU-B")
    assert sku_a is not None
    assert sku_b is not None

    assert sku_a.transaction_fee == 5.98
    assert sku_a.net_profit == -125.98
    assert sku_a.return_count == 1
    assert sku_b.transaction_fee == 2.99
    assert sku_b.net_profit == 8.01
    assert engine.get_loss_makers()[0].sku == "SKU-A"

    dashboard = engine.get_dashboard_response("run001")
    assert dashboard.kpis.total_revenue == 350.0
    assert dashboard.kpis.total_transaction_fees == 8.97
    assert dashboard.kpis.total_net_profit == -117.97
    assert dashboard.kpis.loss_making_sku_count == 1

