import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  ArrowLeft,
  Loader2,
  AlertTriangle,
  TrendingDown,
  TrendingUp,
  Sliders,
  CheckCircle2,
  XCircle,
  Clock,
  FileText,
  DollarSign,
  RotateCcw,
  Megaphone,
  Package,
  ArrowUpRight,
  ArrowDownRight,
  Search,
  MessageSquareWarning,
  ListChecks,
  Sparkles,
  Pencil,
  Save,
  X,
} from "lucide-react";
import { getProductDetail, runSimulation, approveAction, rejectAction, editAction } from "../lib/api";
import type {
  SKUProfitability,
  SimulationResult,
  ActionCard,
  RootCauseAnalysis,
  ActionEditRequest,
  RiskLevel,
} from "../types";

function fmt(n: number): string {
  return new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 }).format(n);
}

function fmtPct(n: number): string {
  return `%${n.toFixed(1)}`;
}

export default function ProductDetailPage() {
  const { runId, sku } = useParams<{ runId: string; sku: string }>();
  const [product, setProduct] = useState<SKUProfitability | null>(null);
  const [rootCause, setRootCause] = useState<RootCauseAnalysis | null>(null);
  const [actions, setActions] = useState<ActionCard[]>([]);
  const [simulation, setSimulation] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [simError, setSimError] = useState("");
  const [actionError, setActionError] = useState("");
  const [editingActionId, setEditingActionId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editReason, setEditReason] = useState("");
  const [editImpact, setEditImpact] = useState("");
  const [editRisk, setEditRisk] = useState<RiskLevel>("low");
  const [savingEdit, setSavingEdit] = useState(false);

  /* ── Simulation Form ─────────────────────────────── */
  const [simPrice, setSimPrice] = useState<string>("");
  const [simAd, setSimAd] = useState<string>("");
  const [simReturn, setSimReturn] = useState<string>("");
  const [simDemand, setSimDemand] = useState<string>("");
  const [simulating, setSimulating] = useState(false);

  useEffect(() => {
    if (!runId || !sku) return;
    getProductDetail(runId, sku)
      .then((intel) => {
        setProduct(intel.profitability);
        setRootCause(intel.root_cause);
        setActions(intel.actions || []);
      })
      .catch((err) => {
        setError(err.response?.data?.detail || "Ürün verileri yüklenemedi.");
      })
      .finally(() => { setLoading(false); });
  }, [runId, sku]);

  const handleSimulate = async () => {
    if (!runId || !sku) return;
    setSimulating(true);
    setSimError("");
    try {
      const res = await runSimulation(runId, sku, {
        new_price: simPrice ? parseFloat(simPrice) : undefined,
        ad_budget_change_pct: simAd ? parseFloat(simAd) : undefined,
        expected_return_rate_change_pct: simReturn ? parseFloat(simReturn) : undefined,
        expected_demand_change_pct: simDemand ? parseFloat(simDemand) : undefined,
      });
      setSimulation(res);
    } catch (err: any) {
      setSimError(err.response?.data?.detail || "Simülasyon çalıştırılamadı.");
    } finally {
      setSimulating(false);
    }
  };

  const handleActionApprove = async (id: string) => {
    setActionError("");
    try {
      const updated = await approveAction(id);
      setActions((prev) => prev.map((a) => (a.action_id === id ? updated : a)));
    } catch (err: any) {
      setActionError(err.response?.data?.detail || "Aksiyon onaylanamadı.");
    }
  };

  const handleActionReject = async (id: string) => {
    setActionError("");
    try {
      const updated = await rejectAction(id);
      setActions((prev) => prev.map((a) => (a.action_id === id ? updated : a)));
    } catch (err: any) {
      setActionError(err.response?.data?.detail || "Aksiyon reddedilemedi.");
    }
  };

  const startEditing = (action: ActionCard) => {
    setEditingActionId(action.action_id);
    setEditTitle(action.title);
    setEditReason(action.reason);
    setEditImpact(action.expected_impact || "");
    setEditRisk(action.risk_level);
  };

  const cancelEditing = () => {
    setEditingActionId(null);
    setEditTitle("");
    setEditReason("");
    setEditImpact("");
    setEditRisk("low");
  };

  const handleActionEdit = async (id: string) => {
    setActionError("");
    setSavingEdit(true);
    try {
      const payload: ActionEditRequest = {
        title: editTitle.trim(),
        reason: editReason.trim(),
        expected_impact: editImpact.trim(),
        risk_level: editRisk,
      };
      const updated = await editAction(id, payload);
      setActions((prev) => prev.map((a) => (a.action_id === id ? updated : a)));
      cancelEditing();
    } catch (err: any) {
      setActionError(err.response?.data?.detail || "Aksiyon duzenlenemedi.");
    } finally {
      setSavingEdit(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="h-8 w-8 animate-spin text-brand-400" />
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <AlertTriangle className="h-10 w-10 text-rose-400" />
        <p className="text-rose-400 font-medium">{error || "Ürün bulunamadı."}</p>
        <Link to={`/dashboard/${runId}`} className="btn-ghost">Dashboard'a Dön</Link>
      </div>
    );
  }

  const isLoss = product.net_profit < 0;

  return (
    <div className="animate-fade-in space-y-6">
      {/* ── Back ───────────────────────────────────── */}
      <Link
        to={`/dashboard/${runId}`}
        className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Dashboard'a Dön
      </Link>

      {/* ── Product Header ─────────────────────────── */}
      <div className="glass-card p-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">{product.product_name}</h1>
            <p className="text-sm text-slate-400 mt-1 font-mono">{product.sku} · {product.category}</p>
          </div>
          <div className={`text-right ${isLoss ? "glow-loss" : "glow-profit"} rounded-xl p-3`}>
            <p className="text-xs text-slate-400 uppercase tracking-wider">Net Sonuç</p>
            <p className={`text-3xl font-extrabold ${isLoss ? "text-rose-400" : "text-emerald-400"}`}>
              {fmt(product.net_profit)} ₺
            </p>
          </div>
        </div>

        {/* Metric grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-4 mt-6">
          {[
            { icon: Package, label: "Satış", value: `${product.quantity_sold} ad.`, color: "text-brand-400" },
            { icon: DollarSign, label: "Ciro", value: `${fmt(product.gross_revenue)} ₺`, color: "text-brand-400" },
            { icon: TrendingUp, label: "Marj", value: fmtPct(product.profit_margin), color: product.profit_margin >= 0 ? "text-emerald-400" : "text-rose-400" },
            { icon: RotateCcw, label: "İade Oranı", value: fmtPct(product.return_rate), color: product.return_rate > 15 ? "text-rose-400" : "text-amber-400" },
            { icon: Megaphone, label: "Reklam/Ciro", value: fmtPct(product.ad_to_revenue_ratio), color: "text-amber-400" },
            { icon: AlertTriangle, label: "Risk Skoru", value: product.risk_score.toFixed(0), color: product.risk_level === "critical" ? "text-rose-400" : "text-amber-400" },
          ].map((m) => (
            <div key={m.label} className="text-center">
              <m.icon className={`h-4 w-4 mx-auto mb-1 ${m.color}`} />
              <p className="text-[10px] text-slate-500 uppercase tracking-wider">{m.label}</p>
              <p className={`text-lg font-bold ${m.color}`}>{m.value}</p>
            </div>
          ))}
        </div>

        {/* Cost breakdown */}
        <div className="mt-6 glass-card p-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Maliyet Dağılımı</p>
          <div className="space-y-2">
            {[
              { label: "Ürün Maliyeti (COGS)", value: product.cogs, color: "bg-slate-500" },
              { label: "Komisyon", value: product.commission_cost, color: "bg-orange-500" },
              { label: "Platform Ücreti", value: product.platform_fee, color: "bg-violet-500" },
              { label: "İşlem Ücreti", value: product.transaction_fee, color: "bg-indigo-500" },
              { label: "Kargo", value: product.shipping_cost, color: "bg-amber-500" },
              { label: "Reklam", value: product.ad_spend, color: "bg-blue-500" },
              { label: "İade Bedeli", value: product.refund_amount, color: "bg-rose-500" },
              { label: "İade Kargo", value: product.return_shipping_cost, color: "bg-pink-500" },
            ].map((c) => {
              const pct = product.gross_revenue > 0 ? (c.value / product.gross_revenue) * 100 : 0;
              return (
                <div key={c.label} className="flex items-center gap-3">
                  <span className="text-xs text-slate-400 w-36 shrink-0">{c.label}</span>
                  <div className="flex-1 h-2 bg-slate-700/50 rounded-full overflow-hidden">
                    <div
                      className={`h-full ${c.color} rounded-full transition-all duration-700`}
                      style={{ width: `${Math.min(pct, 100)}%` }}
                    />
                  </div>
                  <span className="text-xs font-mono text-slate-300 w-20 text-right">
                    {fmt(c.value)} ₺
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Root Cause Analysis (Gemini) ────────────── */}
      {rootCause && rootCause.main_cause && (
        <div className="glass-card p-6 border-brand-500/20 animate-slide-up">
          <div className="flex items-center gap-2 mb-4">
            <Sparkles className="h-5 w-5 text-brand-400" />
            <h2 className="text-lg font-bold">Kök Neden Analizi</h2>
            <span className="badge-info ml-auto">Gemini AI</span>
          </div>

          {/* Main cause */}
          <div className="glass-card p-4 mb-4 border-l-4 border-brand-500">
            <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Ana Neden</p>
            <p className="text-base font-semibold text-white">{rootCause.main_cause}</p>
            {rootCause.main_cause_supporting_refs.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {rootCause.main_cause_supporting_refs.map((ref) => (
                  <span key={ref} className="badge-info">
                    Ref: {ref}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Explanation */}
          {rootCause.explanation && (
            <div className="mb-4">
              <p className="text-xs text-slate-400 uppercase tracking-wider mb-2">Detaylı Açıklama</p>
              <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-line">{rootCause.explanation}</p>
            </div>
          )}

          {/* Review problems */}
          {rootCause.review_problems.length > 0 && (
            <div className="mb-4">
              <div className="flex items-center gap-1.5 mb-2">
                <MessageSquareWarning className="h-4 w-4 text-amber-400" />
                <p className="text-xs text-slate-400 uppercase tracking-wider">Yorumlardaki Problemler</p>
              </div>
              <div className="space-y-1.5">
                {rootCause.review_problems.map((problem, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-amber-400 mt-0.5">•</span>
                    <span className="text-slate-300">{problem}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Return reasons */}
          {Object.keys(rootCause.return_reasons).length > 0 && (
            <div className="mb-4">
              <div className="flex items-center gap-1.5 mb-2">
                <RotateCcw className="h-4 w-4 text-rose-400" />
                <p className="text-xs text-slate-400 uppercase tracking-wider">İade Nedenleri</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(rootCause.return_reasons).map(([reason, count]) => (
                  <span key={reason} className="badge-loss">
                    {reason}: {count}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Description gaps */}
          {rootCause.description_gaps.length > 0 && (
            <div className="mb-4">
              <div className="flex items-center gap-1.5 mb-2">
                <ListChecks className="h-4 w-4 text-blue-400" />
                <p className="text-xs text-slate-400 uppercase tracking-wider">Ürün Açıklaması Eksiklikleri</p>
              </div>
              <div className="space-y-1.5">
                {rootCause.description_gaps.map((gap, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-blue-400 mt-0.5">•</span>
                    <span className="text-slate-300">{gap}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Evidence */}
          {rootCause.evidence.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <Search className="h-4 w-4 text-slate-400" />
                <p className="text-xs text-slate-400 uppercase tracking-wider">
                  Kanıtlar ({rootCause.evidence.length} kaynak)
                </p>
              </div>
              <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                {rootCause.evidence.map((ev, i) => {
                  let badgeClass = "bg-slate-700 text-slate-300";
                  let label = ev.source;
                  if (ev.source === "rag_review" || ev.source === "review") {
                    badgeClass = "bg-blue-500/20 text-blue-400 border border-blue-500/30";
                    label = "💬 Yorum";
                  } else if (ev.source === "product_description") {
                    badgeClass = "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30";
                    label = "📝 Açıklama";
                  } else if (ev.source === "policy") {
                    badgeClass = "bg-purple-500/20 text-purple-400 border border-purple-500/30";
                    label = "📜 Politika";
                  }

                  return (
                    <div key={i} className="glass-card p-3 text-xs">
                      <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium mr-2 mb-1 inline-block ${badgeClass}`}>
                        {label}
                      </span>
                      <span className="text-slate-300 leading-relaxed block mt-1">"{ev.text}"</span>
                      <div className="mt-2 text-[10px] text-slate-500 font-mono">
                        Ref: {ev.reference_id || "-"} | Score: {ev.relevance_score.toFixed(2)}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Scenario Simulator ─────────────────────── */}
      <div className="glass-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Sliders className="h-5 w-5 text-brand-400" />
          <h2 className="text-lg font-bold">Senaryo Simülatörü</h2>
        </div>
        <p className="text-sm text-slate-400 mb-4">
          Fiyat, reklam, iade ve talep değişikliklerini simüle edin. Tüm hesaplar deterministik Python ile yapılır.
        </p>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Yeni Fiyat (₺)</label>
            <input
              type="number"
              placeholder={`Mevcut: ${(product.gross_revenue / product.quantity_sold).toFixed(0)}`}
              value={simPrice}
              onChange={(e) => setSimPrice(e.target.value)}
              className="w-full rounded-xl bg-slate-700/50 border border-slate-600/50 px-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500/40"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Reklam Değişimi (%)</label>
            <input
              type="number"
              placeholder="-30"
              value={simAd}
              onChange={(e) => setSimAd(e.target.value)}
              className="w-full rounded-xl bg-slate-700/50 border border-slate-600/50 px-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500/40"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">İade Oranı Değişimi (%)</label>
            <input
              type="number"
              placeholder="-20"
              value={simReturn}
              onChange={(e) => setSimReturn(e.target.value)}
              className="w-full rounded-xl bg-slate-700/50 border border-slate-600/50 px-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500/40"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Talep Değişimi (%)</label>
            <input
              type="number"
              placeholder="-6"
              value={simDemand}
              onChange={(e) => setSimDemand(e.target.value)}
              className="w-full rounded-xl bg-slate-700/50 border border-slate-600/50 px-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500/40"
            />
          </div>
        </div>

        <button onClick={handleSimulate} disabled={simulating} className="btn-primary">
          {simulating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sliders className="h-4 w-4" />}
          Simülasyonu Çalıştır
        </button>

        {simError && (
          <div className="flex items-center gap-2 text-sm text-rose-400 mt-3">
            <AlertTriangle className="h-4 w-4" />
            {simError}
          </div>
        )}

        {/* Simulation result */}
        {simulation && (
          <div className="mt-6 glass-card p-5 animate-slide-up">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
              <div>
                <p className="text-xs text-slate-400">Mevcut Kâr</p>
                <p className={`text-xl font-bold ${simulation.current_profit >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {fmt(simulation.current_profit)} ₺
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-400">Simüle Kâr</p>
                <p className={`text-xl font-bold ${simulation.simulated_profit >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {fmt(simulation.simulated_profit)} ₺
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-400">Fark</p>
                <p className="text-xl font-bold flex items-center justify-center gap-1">
                  {simulation.profit_delta >= 0 ? (
                    <ArrowUpRight className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <ArrowDownRight className="h-4 w-4 text-rose-400" />
                  )}
                  <span className={simulation.profit_delta >= 0 ? "text-emerald-400" : "text-rose-400"}>
                    {fmt(simulation.profit_delta)} ₺
                  </span>
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-400">Yeni Marj</p>
                <p className={`text-xl font-bold ${simulation.new_margin >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {fmtPct(simulation.new_margin)}
                </p>
              </div>
            </div>
            {simulation.assumptions.length > 0 && (
              <div className="mt-4 border-t border-slate-700/50 pt-3">
                <p className="text-xs text-slate-400 mb-1">Varsayımlar:</p>
                <div className="flex flex-wrap gap-2">
                  {simulation.assumptions.map((a, i) => (
                    <span key={i} className="badge-info">{a}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Action Cards ───────────────────────────── */}
      {actions.length > 0 && (
        <div className="glass-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <FileText className="h-5 w-5 text-emerald-400" />
            <h2 className="text-lg font-bold">Aksiyon Kartları</h2>
            <span className="badge-neutral ml-auto">Human-in-the-Loop</span>
          </div>
          {actionError && (
            <div className="flex items-center gap-2 text-sm text-rose-400 mb-3">
              <AlertTriangle className="h-4 w-4" />
              {actionError}
            </div>
          )}
          <div className="space-y-3">
            {actions.map((action) => (
              <div
                key={action.action_id}
                className={`glass-card-hover p-4 ${
                  action.status === "approved"
                    ? "border-emerald-500/30"
                    : action.status === "rejected"
                    ? "border-rose-500/30 opacity-60"
                    : ""
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      {action.status === "approved" && <CheckCircle2 className="h-4 w-4 text-emerald-400" />}
                      {action.status === "rejected" && <XCircle className="h-4 w-4 text-rose-400" />}
                      {action.status === "pending" && <Clock className="h-4 w-4 text-amber-400" />}
                      <p className="text-sm font-semibold text-white">{action.title}</p>
                    </div>
                    <p className="text-xs text-slate-400">{action.reason}</p>
                    {action.expected_impact && (
                      <p className="text-xs text-slate-500 mt-1">Beklenen etki: {action.expected_impact}</p>
                    )}
                    {editingActionId === action.action_id && (
                      <div className="mt-3 space-y-2 glass-card p-3">
                        <input
                          value={editTitle}
                          onChange={(e) => setEditTitle(e.target.value)}
                          placeholder="Baslik"
                          className="w-full rounded-lg bg-slate-700/50 border border-slate-600/50 px-3 py-2 text-sm text-white"
                        />
                        <textarea
                          value={editReason}
                          onChange={(e) => setEditReason(e.target.value)}
                          placeholder="Gerekce"
                          rows={2}
                          className="w-full rounded-lg bg-slate-700/50 border border-slate-600/50 px-3 py-2 text-sm text-white"
                        />
                        <input
                          value={editImpact}
                          onChange={(e) => setEditImpact(e.target.value)}
                          placeholder="Beklenen etki"
                          className="w-full rounded-lg bg-slate-700/50 border border-slate-600/50 px-3 py-2 text-sm text-white"
                        />
                        <select
                          value={editRisk}
                          onChange={(e) => setEditRisk(e.target.value as RiskLevel)}
                          className="w-full rounded-lg bg-slate-700/50 border border-slate-600/50 px-3 py-2 text-sm text-white"
                        >
                          <option value="low">low</option>
                          <option value="medium">medium</option>
                          <option value="high">high</option>
                          <option value="critical">critical</option>
                        </select>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleActionEdit(action.action_id)}
                            disabled={savingEdit}
                            className="btn-success !py-1.5 !px-3 !text-xs"
                          >
                            {savingEdit ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                            Kaydet
                          </button>
                          <button
                            onClick={cancelEditing}
                            disabled={savingEdit}
                            className="btn-ghost !py-1.5 !px-3 !text-xs"
                          >
                            <X className="h-3.5 w-3.5" />
                            Vazgec
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                  {action.status === "pending" && (
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => handleActionApprove(action.action_id)}
                        className="btn-success !py-1.5 !px-3 !text-xs"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Onayla
                      </button>
                      <button
                        onClick={() => startEditing(action)}
                        className="btn-ghost !py-1.5 !px-3 !text-xs"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                        Duzenle
                      </button>
                      <button
                        onClick={() => handleActionReject(action.action_id)}
                        className="btn-danger !py-1.5 !px-3 !text-xs"
                      >
                        <XCircle className="h-3.5 w-3.5" />
                        Reddet
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
