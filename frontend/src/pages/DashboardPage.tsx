import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Package,
  RotateCcw,
  Megaphone,
  AlertTriangle,
  Wallet,
  ArrowUpRight,
  ArrowDownRight,
  ChevronRight,
  Loader2,
  ShieldAlert,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { getDashboard, getToolTraces } from "../lib/api";
import type { DashboardResponse, MCPToolTrace, SKUProfitability } from "../types";

/* ── Helpers ───────────────────────────────────────── */

function fmt(n: number): string {
  return new Intl.NumberFormat("tr-TR", {
    maximumFractionDigits: 0,
  }).format(n);
}

function fmtPct(n: number): string {
  return `%${n.toFixed(1)}`;
}

function riskColor(level: string): string {
  switch (level) {
    case "critical": return "text-rose-400";
    case "high": return "text-orange-400";
    case "medium": return "text-amber-400";
    default: return "text-emerald-400";
  }
}

function riskBadge(level: string): string {
  switch (level) {
    case "critical": return "badge-loss";
    case "high": return "badge-warning";
    case "medium": return "badge-warning";
    default: return "badge-profit";
  }
}

/* ── Dashboard Page ────────────────────────────────── */

export default function DashboardPage() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [toolTraces, setToolTraces] = useState<MCPToolTrace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!runId) return;
    getDashboard(runId)
      .then(async (d) => {
        setData(d);
        try {
          setToolTraces(await getToolTraces(runId));
        } catch {
          setToolTraces([]);
        }
      })
      .catch((err) => { setError(err.response?.data?.detail || "Dashboard verileri yüklenemedi."); })
      .finally(() => { setLoading(false); });
  }, [runId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="h-8 w-8 animate-spin text-brand-400" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <AlertTriangle className="h-10 w-10 text-rose-400" />
        <p className="text-rose-400 font-medium">{error}</p>
        <button onClick={() => navigate("/")} className="btn-ghost">Ana Sayfaya Dön</button>
      </div>
    );
  }

  if (!data) return null;

  const { kpis, products, loss_makers } = data;

  /* Chart data */
  const chartData = products.map((p) => ({
    name: p.product_name.length > 18 ? p.product_name.slice(0, 18) + "…" : p.product_name,
    profit: Math.round(p.net_profit),
    sku: p.sku,
  }));

  return (
    <div className="animate-fade-in space-y-8">
      {/* ── Header ─────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Profit Control Tower</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Analiz: <span className="text-slate-300 font-mono">{runId}</span>
          </p>
        </div>
      </div>

      {/* ── KPI Cards ──────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <KpiCard
          icon={<DollarSign className="h-5 w-5" />}
          label="Toplam Ciro"
          value={`${fmt(kpis.total_revenue)} ₺`}
          accent="text-brand-400"
        />
        <KpiCard
          icon={kpis.total_net_profit >= 0 ? <TrendingUp className="h-5 w-5" /> : <TrendingDown className="h-5 w-5" />}
          label="Net Kâr"
          value={`${fmt(kpis.total_net_profit)} ₺`}
          accent={kpis.total_net_profit >= 0 ? "text-emerald-400" : "text-rose-400"}
          glow={kpis.total_net_profit < 0}
        />
        <KpiCard
          icon={<Package className="h-5 w-5" />}
          label="Toplam Sipariş"
          value={fmt(kpis.total_orders)}
          accent="text-slate-300"
        />
        <KpiCard
          icon={<RotateCcw className="h-5 w-5" />}
          label="İade Oranı"
          value={fmtPct(kpis.overall_return_rate)}
          accent={kpis.overall_return_rate > 15 ? "text-rose-400" : "text-amber-400"}
        />
        <KpiCard
          icon={<Megaphone className="h-5 w-5" />}
          label="Reklam / Ciro"
          value={fmtPct(kpis.ad_to_revenue_ratio)}
          accent="text-amber-400"
        />
        <KpiCard
          icon={<AlertTriangle className="h-5 w-5" />}
          label="Zarar Eden SKU"
          value={String(kpis.loss_making_sku_count)}
          accent={kpis.loss_making_sku_count > 0 ? "text-rose-400" : "text-emerald-400"}
          glow={kpis.loss_making_sku_count > 0}
        />
        <KpiCard
          icon={<TrendingUp className="h-5 w-5" />}
          label="Ort. Marj"
          value={fmtPct(kpis.average_margin)}
          accent={kpis.average_margin >= 0 ? "text-emerald-400" : "text-rose-400"}
        />
        <KpiCard
          icon={<Wallet className="h-5 w-5" />}
          label="14g Nakit Akışı"
          value={`${fmt(kpis.cashflow_14d)} ₺`}
          accent={kpis.cashflow_14d >= 0 ? "text-emerald-400" : "text-rose-400"}
        />
      </div>

      {/* ── Loss Maker Alert ───────────────────────── */}
      {loss_makers.length > 0 && (
        <div className="glass-card border-rose-500/30 p-6 glow-loss animate-slide-up">
          <div className="flex items-center gap-2 mb-4">
            <ShieldAlert className="h-5 w-5 text-rose-400" />
            <h2 className="text-lg font-bold text-rose-400">
              Çok Satan Ama Zarar Ettiren Ürün{loss_makers.length > 1 ? "ler" : ""} Bulundu
            </h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {loss_makers.map((lm) => (
              <button
                key={lm.sku}
                onClick={() => navigate(`/product/${runId}/${lm.sku}`)}
                className="glass-card-hover p-4 text-left group"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-semibold text-white">{lm.product_name}</span>
                  <ChevronRight className="h-4 w-4 text-slate-500 group-hover:text-white transition-colors" />
                </div>
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div>
                    <p className="text-xs text-slate-400">Satış</p>
                    <p className="text-sm font-bold">{lm.quantity_sold} ad.</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-400">Ciro</p>
                    <p className="text-sm font-bold">{fmt(lm.gross_revenue)} ₺</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-400">Net Sonuç</p>
                    <p className="text-sm font-bold text-rose-400">{fmt(lm.net_profit)} ₺</p>
                  </div>
                </div>
                <div className="mt-3 flex items-center gap-3 text-xs text-slate-400">
                  <span>İade: {fmtPct(lm.return_rate)}</span>
                  <span>Reklam/Ciro: {fmtPct(lm.ad_to_revenue_ratio)}</span>
                  <span className={riskColor(lm.risk_level)}>Risk: {lm.risk_score.toFixed(0)}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="glass-card p-6">
        <h2 className="text-lg font-bold">MCP Tool Trace</h2>
        <p className="text-xs text-slate-400 mt-1">
          Gemini -&gt; MCP Gateway -&gt; finance-mcp -&gt; Tool Result
        </p>
        <div className="mt-4 space-y-2">
          {toolTraces.length === 0 ? (
            <p className="text-xs text-slate-500">Bu run için trace kaydı bulunamadı.</p>
          ) : (
            toolTraces.slice(-6).reverse().map((trace) => (
              <div
                key={trace.trace_id}
                className="rounded-xl border border-slate-700/60 bg-slate-900/40 p-3"
              >
                <p className="text-xs text-slate-300">
                  Gemini requested tool: <span className="font-mono">{trace.tool_name}</span>
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  Route: MCP Gateway -&gt; {trace.server}.{trace.tool_name}
                </p>
                <p className="text-xs mt-1">
                  <span className={trace.status === "success" ? "text-emerald-400" : "text-rose-400"}>
                    Status: {trace.status}
                  </span>
                  {" | "}
                  <span className="text-slate-300">Latency: {trace.latency_ms.toFixed(2)} ms</span>
                </p>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ── Profitability Chart ────────────────────── */}
      <div className="glass-card p-6">
        <h2 className="text-lg font-bold mb-4">SKU Kârlılık Grafiği</h2>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                dataKey="name"
                tick={{ fill: "#94a3b8", fontSize: 11 }}
                angle={-15}
                textAnchor="end"
              />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <Tooltip
                contentStyle={{
                  background: "#1e293b",
                  border: "1px solid #334155",
                  borderRadius: "12px",
                  fontSize: "13px",
                  color: "#f1f5f9",
                }}
                formatter={(value: number) => [`${fmt(value)} ₺`, "Net Kâr"]}
              />
              <Bar dataKey="profit" radius={[6, 6, 0, 0]}>
                {chartData.map((entry) => (
                  <Cell
                    key={entry.sku}
                    fill={entry.profit >= 0 ? "#10b981" : "#f43f5e"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── Product Table ──────────────────────────── */}
      <div className="glass-card overflow-hidden">
        <div className="p-5 border-b border-slate-700/50">
          <h2 className="text-lg font-bold">Ürün Detay Tablosu</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Ürün</th>
                <th className="text-right">Satış</th>
                <th className="text-right">Ciro</th>
                <th className="text-right">Net Kâr</th>
                <th className="text-right">Marj</th>
                <th className="text-right">İade</th>
                <th className="text-center">Risk</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {products.map((p) => (
                <tr key={p.sku} onClick={() => navigate(`/product/${runId}/${p.sku}`)}>
                  <td>
                    <div>
                      <p className="font-medium text-white">{p.product_name}</p>
                      <p className="text-xs text-slate-500">{p.sku}</p>
                    </div>
                  </td>
                  <td className="text-right font-mono">{p.quantity_sold}</td>
                  <td className="text-right font-mono">{fmt(p.gross_revenue)} ₺</td>
                  <td className="text-right font-mono">
                    <span className={`flex items-center justify-end gap-1 ${p.net_profit >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {p.net_profit >= 0 ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                      {fmt(p.net_profit)} ₺
                    </span>
                  </td>
                  <td className="text-right font-mono">
                    <span className={p.profit_margin >= 0 ? "text-emerald-400" : "text-rose-400"}>
                      {fmtPct(p.profit_margin)}
                    </span>
                  </td>
                  <td className="text-right font-mono">
                    <span className={p.return_rate > 15 ? "text-rose-400" : "text-slate-300"}>
                      {fmtPct(p.return_rate)}
                    </span>
                  </td>
                  <td className="text-center">
                    <span className={riskBadge(p.risk_level)}>
                      {p.risk_score.toFixed(0)}
                    </span>
                  </td>
                  <td>
                    <ChevronRight className="h-4 w-4 text-slate-600" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

/* ── KPI Card Component ────────────────────────────── */

function KpiCard({
  icon,
  label,
  value,
  accent,
  glow,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  accent: string;
  glow?: boolean;
}) {
  return (
    <div className={`kpi-card animate-slide-up ${glow ? "glow-loss" : ""}`}>
      <div className={`${accent} mb-1`}>{icon}</div>
      <p className="kpi-label">{label}</p>
      <p className={`kpi-value ${accent}`}>{value}</p>
    </div>
  );
}
