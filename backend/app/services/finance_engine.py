"""Deterministic Finance Engine — SKU profitability, risk scores, cashflow.

All financial calculations are done with Python/Pandas. NO LLM involved.
This is a deliberate architectural decision for accuracy and auditability.
"""

from __future__ import annotations

import logging
import pandas as pd
from pathlib import Path

from app.config import settings
from app.models.schemas import (
    SKUProfitability,
    DashboardKPIs,
    DashboardResponse,
    RiskLevel,
)

logger = logging.getLogger(__name__)


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
            xls = run_dir / f"{name}.xls"
            if csv.exists():
                return pd.read_csv(csv)
            elif xlsx.exists():
                return pd.read_excel(xlsx)
            elif xls.exists():
                return pd.read_excel(xls)
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
        if "quantity" in orders.columns:
            raw_quantity = orders["quantity"]
        else:
            raw_quantity = pd.Series(0, index=orders.index, dtype="float64")

        if "unit_price" in orders.columns:
            raw_unit_price = orders["unit_price"]
        else:
            raw_unit_price = pd.Series(0.0, index=orders.index, dtype="float64")

        orders["quantity"] = pd.to_numeric(raw_quantity, errors="coerce").fillna(0)
        orders["unit_price"] = pd.to_numeric(raw_unit_price, errors="coerce").fillna(0.0)
        orders["quantity"] = orders["quantity"].clip(lower=0)
        orders["unit_price"] = orders["unit_price"].clip(lower=0)
        if "order_id" in orders.columns:
            orders["order_key"] = orders["order_id"].astype(str)
            order_count_agg: tuple[str, str] = ("order_key", "nunique")
        else:
            # Fallback when order id is missing: treat each row as one order event.
            orders["order_key"] = orders.index.astype(str)
            order_count_agg = ("order_key", "count")

        # Revenue per SKU
        sku_revenue = orders.groupby("sku").agg(
            order_count=order_count_agg,
            quantity_sold=("quantity", "sum"),
            gross_revenue=("unit_price", lambda x: (x * orders.loc[x.index, "quantity"]).sum()),
        ).reset_index()

        # Commission per SKU
        if "commission_rate" in orders.columns:
            orders["commission_rate"] = pd.to_numeric(orders["commission_rate"], errors="coerce").fillna(0.0)
            orders["commission_cost"] = orders["unit_price"] * orders["quantity"] * orders["commission_rate"]
            sku_commission = orders.groupby("sku")["commission_cost"].sum().reset_index()
            sku_revenue = sku_revenue.merge(sku_commission, on="sku", how="left")
        else:
            sku_revenue["commission_cost"] = 0.0

        # Platform fee per SKU
        if "platform_fee" in orders.columns:
            orders["platform_fee"] = pd.to_numeric(orders["platform_fee"], errors="coerce").fillna(0.0)
            sku_platform_fee = orders.groupby("sku")["platform_fee"].sum().reset_index()
            sku_revenue = sku_revenue.merge(sku_platform_fee, on="sku", how="left")
        elif "platform_fee_rate" in orders.columns:
            orders["platform_fee_rate"] = pd.to_numeric(orders["platform_fee_rate"], errors="coerce").fillna(0.0)
            orders["platform_fee"] = orders["unit_price"] * orders["quantity"] * orders["platform_fee_rate"]
            sku_platform_fee = orders.groupby("sku")["platform_fee"].sum().reset_index()
            sku_revenue = sku_revenue.merge(sku_platform_fee, on="sku", how="left")
        else:
            sku_revenue["platform_fee"] = 0.0

        # Transaction fee per SKU
        if "transaction_fee" in orders.columns:
            orders["transaction_fee"] = pd.to_numeric(orders["transaction_fee"], errors="coerce").fillna(0.0)
            sku_transaction_fee = orders.groupby("sku")["transaction_fee"].sum().reset_index()
            sku_revenue = sku_revenue.merge(sku_transaction_fee, on="sku", how="left")
        else:
            # Default platform transaction fee on each order row
            orders["transaction_fee"] = settings.TRANSACTION_FEE_PER_ORDER
            sku_transaction_fee = orders.groupby("sku")["transaction_fee"].sum().reset_index()
            sku_revenue = sku_revenue.merge(sku_transaction_fee, on="sku", how="left")

        # Shipping per SKU
        if "cargo_cost" in orders.columns:
            orders["cargo_cost"] = pd.to_numeric(orders["cargo_cost"], errors="coerce").fillna(0.0)
            sku_shipping = orders.groupby("sku")["cargo_cost"].sum().reset_index(name="shipping_cost")
            sku_revenue = sku_revenue.merge(sku_shipping, on="sku", how="left")
        else:
            sku_revenue["shipping_cost"] = 0.0

        # Ad spend per SKU
        if not self.ads.empty and "sku" in self.ads.columns:
            ads = self.ads.copy()
            if "spend" in ads.columns:
                raw_spend = ads["spend"]
            else:
                raw_spend = pd.Series(0.0, index=ads.index, dtype="float64")
            ads["spend"] = pd.to_numeric(raw_spend, errors="coerce").fillna(0.0)
            sku_ads = ads.groupby("sku")["spend"].sum().reset_index()
            sku_ads.columns = ["sku", "ad_spend"]
            sku_revenue = sku_revenue.merge(sku_ads, on="sku", how="left")
        else:
            sku_revenue["ad_spend"] = 0.0

        # Returns per SKU
        if not self.returns.empty and "sku" in self.returns.columns:
            returns = self.returns.copy()
            return_count_col = "return_id" if "return_id" in returns.columns else "sku"
            returns["return_count"] = 1

            if "refund_amount" in returns.columns:
                returns["refund_amount"] = pd.to_numeric(returns["refund_amount"], errors="coerce").fillna(0.0)
            elif "order_id" in returns.columns and "order_id" in orders.columns:
                order_amount_map = (
                    (orders["unit_price"] * orders["quantity"])
                    .groupby(orders["order_id"])
                    .sum()
                )
                returns["refund_amount"] = (
                    returns["order_id"].map(order_amount_map).fillna(0.0)
                )
            else:
                logger.warning(
                    "returns dataset has no refund_amount/order_id mapping; "
                    "refund_amount defaults to 0.0"
                )
                returns["refund_amount"] = 0.0

            if "return_shipping_cost" in returns.columns:
                returns["return_shipping_cost"] = pd.to_numeric(
                    returns["return_shipping_cost"], errors="coerce"
                ).fillna(0.0)
            else:
                returns["return_shipping_cost"] = 0.0

            sku_returns = returns.groupby("sku").agg(
                return_count=(return_count_col, "count"),
                refund_amount=("refund_amount", "sum"),
                return_shipping_cost=("return_shipping_cost", "sum"),
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
            - sku_revenue["platform_fee"]
            - sku_revenue["transaction_fee"]
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
                order_count=int(row.get("order_count", 0)),
                quantity_sold=int(row["quantity_sold"]),
                gross_revenue=round(row["gross_revenue"], 2),
                cogs=round(row["cogs"], 2),
                commission_cost=round(row["commission_cost"], 2),
                platform_fee=round(row["platform_fee"], 2),
                transaction_fee=round(row["transaction_fee"], 2),
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
        # Absolute risk components (not cohort-normalized) so equal-loss cohorts
        # still receive meaningful risk scores.
        safe_revenue = df["gross_revenue"].replace(0, 1.0)
        loss_ratio_pct = ((-df["net_profit"]).clip(lower=0) / safe_revenue) * 100
        profit_score = loss_ratio_pct.clip(0, 100)
        return_score = df["return_rate"].clip(0, 100)
        ad_score = df["ad_to_revenue_ratio"].clip(0, 100)

        weight_profit = 0.40
        weight_return = 0.35
        weight_ad = 0.25
        total_weight = weight_profit + weight_return + weight_ad
        risk = (
            profit_score * weight_profit
            + return_score * weight_return
            + ad_score * weight_ad
        ) / total_weight

        # Any loss-making SKU should not appear as low-risk, even in homogeneous cohorts.
        loss_floor = 30.0
        risk = risk.where(df["net_profit"] >= 0, risk.clip(lower=loss_floor))

        # Ensure 0-100
        return risk.clip(0, 100)

    # ── KPIs ───────────────────────────────────────────

    def _calculate_kpis(self):
        products = list(self.profitability.values())
        if not products:
            return

        total_revenue = sum(p.gross_revenue for p in products)
        total_profit = sum(p.net_profit for p in products)
        total_platform_fees = sum(p.platform_fee for p in products)
        total_transaction_fees = sum(p.transaction_fee for p in products)
        total_orders = sum(p.quantity_sold for p in products)
        total_returns = sum(p.return_count for p in products)
        total_ad = sum(p.ad_spend for p in products)
        loss_makers = [p for p in products if p.net_profit < 0]

        most_risky = max(products, key=lambda p: p.risk_score) if products else None

        self.kpis = DashboardKPIs(
            total_revenue=round(total_revenue, 2),
            total_net_profit=round(total_profit, 2),
            total_platform_fees=round(total_platform_fees, 2),
            total_transaction_fees=round(total_transaction_fees, 2),
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
        """Simple 14-day cashflow estimate based on actual data date range."""
        products = list(self.profitability.values())
        if not products:
            return 0.0

        # Determine actual date range from orders data
        data_days = 30  # fallback
        if hasattr(self, "orders") and not self.orders.empty and "order_date" in self.orders.columns:
            try:
                dates = pd.to_datetime(self.orders["order_date"], errors="coerce").dropna()
                if len(dates) >= 2:
                    delta = (dates.max() - dates.min()).days
                    if delta > 0:
                        data_days = delta
            except Exception:
                pass  # keep fallback

        total_revenue = sum(p.gross_revenue for p in products)
        total_costs = sum(
            p.cogs
            + p.commission_cost
            + p.platform_fee
            + p.transaction_fee
            + p.shipping_cost
            + p.ad_spend
            + p.refund_amount
            + p.return_shipping_cost
            for p in products
        )

        daily_revenue = total_revenue / data_days
        daily_cost = total_costs / data_days

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
