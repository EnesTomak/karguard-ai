"""Deterministic Finance Engine — SKU profitability, risk scores, cashflow.

All financial calculations are done with Python/Pandas. NO LLM involved.
This is a deliberate architectural decision for accuracy and auditability.
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path

from app.models.schemas import (
    SKUProfitability,
    DashboardKPIs,
    DashboardResponse,
    RiskLevel,
)


class FinanceEngine:
    """Calculates SKU-level profitability and risk scores from raw CSV data."""

    # Class-level cache
    _cache: dict[str, "FinanceEngine"] = {}

    def __init__(self):
        self.orders: pd.DataFrame = pd.DataFrame()
        self.returns: pd.DataFrame = pd.DataFrame()
        self.products: pd.DataFrame = pd.DataFrame()
        self.ads: pd.DataFrame = pd.DataFrame()
        self.profitability: dict[str, SKUProfitability] = {}
        self.kpis: DashboardKPIs = DashboardKPIs()

    # ── Factory ────────────────────────────────────────

    @classmethod
    def from_directory(cls, run_dir: Path) -> "FinanceEngine":
        engine = cls()
        engine._load_data(run_dir)
        engine._calculate_profitability()
        engine._calculate_kpis()
        return engine

    @classmethod
    def get_cached(cls, run_id: str) -> "FinanceEngine | None":
        return cls._cache.get(run_id)

    def cache(self, run_id: str):
        FinanceEngine._cache[run_id] = self

    # ── Data Loading ───────────────────────────────────

    def _load_data(self, run_dir: Path):
        def read(name: str) -> pd.DataFrame:
            csv = run_dir / f"{name}.csv"
            xlsx = run_dir / f"{name}.xlsx"
            if csv.exists():
                return pd.read_csv(csv)
            elif xlsx.exists():
                return pd.read_excel(xlsx)
            return pd.DataFrame()

        self.orders = read("orders")
        self.returns = read("returns")
        self.products = read("products")
        self.ads = read("ads")

    # ── Core Calculation ───────────────────────────────

    def _calculate_profitability(self):
        if self.orders.empty or self.products.empty:
            return

        # Merge product info
        orders = self.orders.copy()

        # Revenue per SKU
        sku_revenue = orders.groupby("sku").agg(
            quantity_sold=("quantity", "sum"),
            gross_revenue=("unit_price", lambda x: (x * orders.loc[x.index, "quantity"]).sum()),
        ).reset_index()

        # Commission per SKU
        if "commission_rate" in orders.columns:
            orders["commission_cost"] = orders["unit_price"] * orders["quantity"] * orders["commission_rate"]
            sku_commission = orders.groupby("sku")["commission_cost"].sum().reset_index()
            sku_revenue = sku_revenue.merge(sku_commission, on="sku", how="left")
        else:
            sku_revenue["commission_cost"] = 0.0

        # Shipping per SKU
        if "cargo_cost" in orders.columns:
            sku_shipping = orders.groupby("sku")["cargo_cost"].sum().reset_index(name="shipping_cost")
            sku_revenue = sku_revenue.merge(sku_shipping, on="sku", how="left")
        else:
            sku_revenue["shipping_cost"] = 0.0

        # Ad spend per SKU
        if not self.ads.empty and "sku" in self.ads.columns:
            sku_ads = self.ads.groupby("sku")["spend"].sum().reset_index()
            sku_ads.columns = ["sku", "ad_spend"]
            sku_revenue = sku_revenue.merge(sku_ads, on="sku", how="left")
        else:
            sku_revenue["ad_spend"] = 0.0

        # Returns per SKU
        if not self.returns.empty and "sku" in self.returns.columns:
            sku_returns = self.returns.groupby("sku").agg(
                return_count=("return_id", "count"),
                refund_amount=("refund_amount", "sum") if "refund_amount" in self.returns.columns else ("return_id", "count"),
                return_shipping_cost=("return_shipping_cost", "sum") if "return_shipping_cost" in self.returns.columns else ("return_id", lambda x: 0),
            ).reset_index()
            sku_revenue = sku_revenue.merge(sku_returns, on="sku", how="left")
        else:
            sku_revenue["return_count"] = 0
            sku_revenue["refund_amount"] = 0.0
            sku_revenue["return_shipping_cost"] = 0.0

        # COGS from products
        if "unit_cost" in self.products.columns:
            product_costs = self.products[["sku", "unit_cost"]].copy()
            sku_revenue = sku_revenue.merge(product_costs, on="sku", how="left")
            sku_revenue["cogs"] = sku_revenue["unit_cost"].fillna(0) * sku_revenue["quantity_sold"]
        else:
            sku_revenue["cogs"] = 0.0

        # Product names
        if "name" in self.products.columns:
            sku_revenue = sku_revenue.merge(
                self.products[["sku", "name", "category"]].drop_duplicates("sku"),
                on="sku", how="left",
            )
        else:
            sku_revenue["name"] = sku_revenue["sku"]
            sku_revenue["category"] = ""

        # Fill NaN
        sku_revenue = sku_revenue.fillna(0)

        # Calculate net profit
        sku_revenue["net_profit"] = (
            sku_revenue["gross_revenue"]
            - sku_revenue["cogs"]
            - sku_revenue["commission_cost"]
            - sku_revenue["shipping_cost"]
            - sku_revenue["ad_spend"]
            - sku_revenue["refund_amount"]
            - sku_revenue["return_shipping_cost"]
        )

        # Margins and ratios
        sku_revenue["profit_margin"] = sku_revenue.apply(
            lambda r: (r["net_profit"] / r["gross_revenue"] * 100) if r["gross_revenue"] > 0 else 0, axis=1
        )
        sku_revenue["return_rate"] = sku_revenue.apply(
            lambda r: (r["return_count"] / r["quantity_sold"] * 100) if r["quantity_sold"] > 0 else 0, axis=1
        )
        sku_revenue["ad_to_revenue_ratio"] = sku_revenue.apply(
            lambda r: (r["ad_spend"] / r["gross_revenue"] * 100) if r["gross_revenue"] > 0 else 0, axis=1
        )

        # Risk score
        sku_revenue["risk_score"] = self._calculate_risk_scores(sku_revenue)

        # Build SKUProfitability objects
        for _, row in sku_revenue.iterrows():
            score = row["risk_score"]
            if score >= 75:
                level = RiskLevel.CRITICAL
            elif score >= 50:
                level = RiskLevel.HIGH
            elif score >= 25:
                level = RiskLevel.MEDIUM
            else:
                level = RiskLevel.LOW

            self.profitability[row["sku"]] = SKUProfitability(
                sku=row["sku"],
                product_name=row.get("name", row["sku"]),
                category=row.get("category", ""),
                quantity_sold=int(row["quantity_sold"]),
                gross_revenue=round(row["gross_revenue"], 2),
                cogs=round(row["cogs"], 2),
                commission_cost=round(row["commission_cost"], 2),
                shipping_cost=round(row["shipping_cost"], 2),
                ad_spend=round(row["ad_spend"], 2),
                return_count=int(row["return_count"]),
                return_rate=round(row["return_rate"], 2),
                refund_amount=round(row["refund_amount"], 2),
                return_shipping_cost=round(row["return_shipping_cost"], 2),
                net_profit=round(row["net_profit"], 2),
                profit_margin=round(row["profit_margin"], 2),
                ad_to_revenue_ratio=round(row["ad_to_revenue_ratio"], 2),
                risk_score=round(score, 2),
                risk_level=level,
            )

    def _calculate_risk_scores(self, df: pd.DataFrame) -> pd.Series:
        """Weighted risk score: 0-100. Higher = worse."""

        def normalize(series: pd.Series) -> pd.Series:
            mn, mx = series.min(), series.max()
            if mx == mn:
                return pd.Series(0, index=series.index)
            return ((series - mn) / (mx - mn)) * 100

        # Negative profit score (more negative = higher risk)
        # -net_profit turns losses into positive values, clip(lower=0) ignores profitable SKUs
        profit_score = normalize((-df["net_profit"]).clip(lower=0))

        # Return rate
        return_score = normalize(df["return_rate"])

        # Ad to revenue
        ad_score = normalize(df["ad_to_revenue_ratio"])
        # Composite
        risk = (
            profit_score * 0.40
            + return_score * 0.30
            + ad_score * 0.20
        )

        # Ensure 0-100
        return risk.clip(0, 100)

    # ── KPIs ───────────────────────────────────────────

    def _calculate_kpis(self):
        products = list(self.profitability.values())
        if not products:
            return

        total_revenue = sum(p.gross_revenue for p in products)
        total_profit = sum(p.net_profit for p in products)
        total_orders = sum(p.quantity_sold for p in products)
        total_returns = sum(p.return_count for p in products)
        total_ad = sum(p.ad_spend for p in products)
        loss_makers = [p for p in products if p.net_profit < 0]

        most_risky = max(products, key=lambda p: p.risk_score) if products else None

        self.kpis = DashboardKPIs(
            total_revenue=round(total_revenue, 2),
            total_net_profit=round(total_profit, 2),
            average_margin=round(total_profit / total_revenue * 100, 2) if total_revenue > 0 else 0,
            total_orders=total_orders,
            total_returns=total_returns,
            overall_return_rate=round(total_returns / total_orders * 100, 2) if total_orders > 0 else 0,
            ad_to_revenue_ratio=round(total_ad / total_revenue * 100, 2) if total_revenue > 0 else 0,
            loss_making_sku_count=len(loss_makers),
            most_risky_product=most_risky.product_name if most_risky else "",
            cashflow_14d=round(self._forecast_cashflow_14d(), 2),
        )

    def _forecast_cashflow_14d(self) -> float:
        """Simple 14-day cashflow estimate."""
        products = list(self.profitability.values())
        if not products:
            return 0.0

        # Rough daily estimates from totals
        total_revenue = sum(p.gross_revenue for p in products)
        total_costs = sum(
            p.cogs + p.commission_cost + p.shipping_cost + p.ad_spend + p.refund_amount
            for p in products
        )

        # Assume data covers ~30 days, project to 14
        daily_revenue = total_revenue / 30
        daily_cost = total_costs / 30

        return (daily_revenue - daily_cost) * 14

    # ── Accessors ──────────────────────────────────────

    def get_all_products(self) -> list[SKUProfitability]:
        return sorted(self.profitability.values(), key=lambda p: p.risk_score, reverse=True)

    def get_product(self, sku: str) -> SKUProfitability | None:
        return self.profitability.get(sku)

    def get_loss_makers(self) -> list[SKUProfitability]:
        return [p for p in self.profitability.values() if p.net_profit < 0]

    def get_dashboard_response(self, run_id: str) -> DashboardResponse:
        return DashboardResponse(
            run_id=run_id,
            kpis=self.kpis,
            products=self.get_all_products(),
            loss_makers=self.get_loss_makers(),
        )
