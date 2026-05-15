from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────

class AnalysisStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ActionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── Upload & Run ───────────────────────────────────────

class UploadResponse(BaseModel):
    run_id: str
    uploaded_files: list[str]
    message: str


class AnalysisRunResponse(BaseModel):
    run_id: str
    status: AnalysisStatus
    created_at: str
    agent_steps: list[AgentStepResponse] = []


# ── Agent ──────────────────────────────────────────────

class AgentStepResponse(BaseModel):
    step_name: str
    status: str  # "running" | "completed" | "failed"
    message: str = ""
    timestamp: str = ""


# ── Finance ────────────────────────────────────────────

class SKUProfitability(BaseModel):
    sku: str
    product_name: str
    category: str = ""
    order_count: int = 0
    quantity_sold: int = 0
    gross_revenue: float = 0.0
    cogs: float = 0.0
    commission_cost: float = 0.0
    platform_fee: float = 0.0
    transaction_fee: float = 0.0
    shipping_cost: float = 0.0
    ad_spend: float = 0.0
    return_count: int = 0
    return_rate: float = 0.0
    refund_amount: float = 0.0
    return_shipping_cost: float = 0.0
    net_profit: float = 0.0
    profit_margin: float = 0.0
    ad_to_revenue_ratio: float = 0.0
    risk_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW


class DashboardKPIs(BaseModel):
    total_revenue: float = 0.0
    total_net_profit: float = 0.0
    total_platform_fees: float = 0.0
    total_transaction_fees: float = 0.0
    average_margin: float = 0.0
    total_orders: int = 0
    total_returns: int = 0
    overall_return_rate: float = 0.0
    ad_to_revenue_ratio: float = 0.0
    loss_making_sku_count: int = 0
    most_risky_product: str = ""
    cashflow_14d: float = 0.0


class DashboardResponse(BaseModel):
    run_id: str
    kpis: DashboardKPIs
    products: list[SKUProfitability]
    loss_makers: list[SKUProfitability]


# ── Root Cause & Insights ──────────────────────────────

class EvidenceItem(BaseModel):
    source: str  # "review" | "return" | "product_description" | "policy"
    text: str
    reference_id: str = ""
    relevance_score: float = 0.0


class RootCauseAnalysis(BaseModel):
    sku: str
    product_name: str
    main_cause: str = ""
    explanation: str = ""
    evidence: list[EvidenceItem] = []
    main_cause_supporting_refs: list[str] = []
    review_problems: list[str] = []
    return_reasons: dict[str, int] = {}
    description_gaps: list[str] = []


class ProductIntelligence(BaseModel):
    profitability: SKUProfitability
    root_cause: RootCauseAnalysis
    simulations: list[SimulationResult] = []
    actions: list[ActionCard] = []


# ── Simulation ─────────────────────────────────────────

class SimulationRequest(BaseModel):
    new_price: Optional[float] = None
    ad_budget_change_pct: Optional[float] = None
    expected_return_rate_change_pct: Optional[float] = None
    expected_demand_change_pct: Optional[float] = None


class SimulationResult(BaseModel):
    scenario_label: str = ""
    current_profit: float = 0.0
    simulated_profit: float = 0.0
    profit_delta: float = 0.0
    new_margin: float = 0.0
    assumptions: list[str] = []


# ── Actions ────────────────────────────────────────────

class ActionCard(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    sku: str
    action_type: str  # "price_change" | "ad_budget" | "description_update" | "stock_pause" | "customer_reply"
    title: str
    reason: str
    expected_impact: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    status: ActionStatus = ActionStatus.PENDING


class ActionApprovalRequest(BaseModel):
    action: str  


class ActionEditRequest(BaseModel):
    action_type: Optional[str] = None
    title: Optional[str] = None
    reason: Optional[str] = None
    expected_impact: Optional[str] = None
    risk_level: Optional[RiskLevel] = None


# Fix forward references
AnalysisRunResponse.model_rebuild()
ProductIntelligence.model_rebuild()
