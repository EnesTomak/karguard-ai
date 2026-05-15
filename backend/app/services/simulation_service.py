"""Scenario simulation — what-if analysis for price/ad/return changes."""

from app.models.schemas import SKUProfitability, SimulationRequest, SimulationResult


def run_simulation(product: SKUProfitability, req: SimulationRequest) -> SimulationResult:
    """Run a deterministic what-if scenario on a single SKU."""

    current_price = product.gross_revenue / product.quantity_sold if product.quantity_sold > 0 else 0
    current_quantity = product.quantity_sold
    current_ad = product.ad_spend
    current_return_rate = product.return_rate / 100
    current_order_count = product.order_count if product.order_count > 0 else 0

    # Apply changes
    new_price = req.new_price if req.new_price is not None else current_price
    demand_change = (req.expected_demand_change_pct or 0) / 100
    ad_change = (req.ad_budget_change_pct or 0) / 100
    return_change = (req.expected_return_rate_change_pct or 0) / 100
    if new_price < 0:
        raise ValueError("new_price cannot be negative.")
    if demand_change < -1:
        raise ValueError("expected_demand_change_pct cannot be less than -100.")
    if ad_change < -1:
        raise ValueError("ad_budget_change_pct cannot be less than -100.")

    # New quantities
    new_quantity = max(0, int(round(current_quantity * (1 + demand_change))))
    new_ad = max(0.0, current_ad * (1 + ad_change))
    new_return_rate = max(0, current_return_rate * (1 + return_change))
    new_return_count = int(new_quantity * new_return_rate)
    if current_order_count <= 0 and current_quantity > 0:
        # Backward-compatible fallback for older snapshots that lack order_count.
        current_order_count = current_quantity

    # Revenue
    new_revenue = new_price * new_quantity

    # Costs (scale proportionally)
    unit_cost = product.cogs / product.quantity_sold if product.quantity_sold > 0 else 0
    commission_rate = product.commission_cost / product.gross_revenue if product.gross_revenue > 0 else 0
    platform_fee_rate = product.platform_fee / product.gross_revenue if product.gross_revenue > 0 else 0
    avg_units_per_order = (
        (current_quantity / current_order_count)
        if current_order_count > 0 and current_quantity > 0
        else 0
    )
    estimated_new_orders = (
        (new_quantity / avg_units_per_order)
        if avg_units_per_order > 0
        else float(new_quantity)
    )
    transaction_fee_per_order = (
        product.transaction_fee / current_order_count
        if current_order_count > 0
        else 0
    )
    shipping_per_order = (
        product.shipping_cost / current_order_count
        if current_order_count > 0
        else 0
    )
    refund_per_return = product.refund_amount / product.return_count if product.return_count > 0 else new_price
    return_ship_per = product.return_shipping_cost / product.return_count if product.return_count > 0 else 0

    new_cogs = unit_cost * new_quantity
    new_commission = new_revenue * commission_rate
    new_platform_fee = new_revenue * platform_fee_rate
    new_transaction_fee = transaction_fee_per_order * estimated_new_orders
    new_shipping = shipping_per_order * estimated_new_orders
    new_refund = refund_per_return * new_return_count
    new_return_shipping = return_ship_per * new_return_count

    simulated_profit = (
        new_revenue - new_cogs - new_commission - new_platform_fee - new_transaction_fee - new_shipping
        - new_ad - new_refund - new_return_shipping
    )
    new_margin = (simulated_profit / new_revenue * 100) if new_revenue > 0 else 0

    # Assumptions
    assumptions = []
    if req.new_price is not None:
        assumptions.append(f"Fiyat: {current_price:.0f} TL → {new_price:.0f} TL")
    if req.ad_budget_change_pct is not None:
        assumptions.append(f"Reklam bütçesi: %{req.ad_budget_change_pct:+.0f}")
    if req.expected_return_rate_change_pct is not None:
        assumptions.append(f"İade oranı: %{req.expected_return_rate_change_pct:+.0f}")
    if req.expected_demand_change_pct is not None:
        assumptions.append(f"Talep değişimi: %{req.expected_demand_change_pct:+.0f}")
    assumptions.append(f"Tahmini siparis adedi: {estimated_new_orders:.2f}")

    return SimulationResult(
        scenario_label="Özel Senaryo",
        current_profit=round(product.net_profit, 2),
        simulated_profit=round(simulated_profit, 2),
        profit_delta=round(simulated_profit - product.net_profit, 2),
        new_margin=round(new_margin, 2),
        assumptions=assumptions,
    )
