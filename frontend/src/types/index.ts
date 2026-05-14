/* ── Backend API response types (mirrors Pydantic schemas) ── */

export type RiskLevel = "low" | "medium" | "high" | "critical";
export type AnalysisStatus = "pending" | "running" | "completed" | "failed";
export type ActionStatus = "pending" | "approved" | "rejected";

export interface UploadResponse {
  run_id: string;
  uploaded_files: string[];
  message: string;
}

export interface AgentStep {
  step_name: string;
  status: string;
  message: string;
  timestamp: string;
}

export interface AnalysisRunResponse {
  run_id: string;
  status: AnalysisStatus;
  created_at: string;
  agent_steps: AgentStep[];
}

export interface SKUProfitability {
  sku: string;
  product_name: string;
  category: string;
  quantity_sold: number;
  gross_revenue: number;
  cogs: number;
  commission_cost: number;
  shipping_cost: number;
  ad_spend: number;
  return_count: number;
  return_rate: number;
  refund_amount: number;
  return_shipping_cost: number;
  net_profit: number;
  profit_margin: number;
  ad_to_revenue_ratio: number;
  risk_score: number;
  risk_level: RiskLevel;
}

export interface DashboardKPIs {
  total_revenue: number;
  total_net_profit: number;
  average_margin: number;
  total_orders: number;
  total_returns: number;
  overall_return_rate: number;
  ad_to_revenue_ratio: number;
  loss_making_sku_count: number;
  most_risky_product: string;
  cashflow_14d: number;
}

export interface DashboardResponse {
  run_id: string;
  kpis: DashboardKPIs;
  products: SKUProfitability[];
  loss_makers: SKUProfitability[];
}

export interface EvidenceItem {
  source: string;
  text: string;
  reference_id: string;
  relevance_score: number;
}

export interface RootCauseAnalysis {
  sku: string;
  product_name: string;
  main_cause: string;
  explanation: string;
  evidence: EvidenceItem[];
  review_problems: string[];
  return_reasons: Record<string, number>;
  description_gaps: string[];
}

export interface ProductIntelligence {
  profitability: SKUProfitability;
  root_cause: RootCauseAnalysis;
  simulations: SimulationResult[];
  actions: ActionCard[];
}

export interface SimulationRequest {
  new_price?: number;
  ad_budget_change_pct?: number;
  expected_return_rate_change_pct?: number;
  expected_demand_change_pct?: number;
}

export interface SimulationResult {
  scenario_label: string;
  current_profit: number;
  simulated_profit: number;
  profit_delta: number;
  new_margin: number;
  assumptions: string[];
}

export interface ActionCard {
  action_id: string;
  sku: string;
  action_type: string;
  title: string;
  reason: string;
  expected_impact: string;
  risk_level: RiskLevel;
  status: ActionStatus;
}
