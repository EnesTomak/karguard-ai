import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Upload,
  FileSpreadsheet,
  X,
  ArrowRight,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  BarChart3,
  ShieldCheck,
  TrendingDown,
} from "lucide-react";
import { uploadFiles, startAnalysis } from "../lib/api";
import type { AgentStep } from "../types";

const ACCEPTED = ".csv,.xlsx,.xls,.md,.txt";

export default function UploadPage() {
  const navigate = useNavigate();
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([]);
  const [error, setError] = useState("");

  /* ── Drag & Drop ─────────────────────────────────── */

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const dropped = Array.from(e.dataTransfer.files);
    setFiles((prev) => [...prev, ...dropped]);
  }, []);

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
    }
  };

  const removeFile = (idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  /* ── Upload & Analyze ────────────────────────────── */

  const handleStart = async () => {
    if (files.length === 0) return;
    setError("");
    setUploading(true);

    try {
      const uploadRes = await uploadFiles(files);
      setUploading(false);
      setAnalyzing(true);

      const analysisRes = await startAnalysis(uploadRes.run_id);

      // Progressive step reveal for visual feedback
      for (let i = 0; i < analysisRes.agent_steps.length; i++) {
        setAgentSteps(analysisRes.agent_steps.slice(0, i + 1));
        await new Promise((r) => setTimeout(r, 400));
      }

      // Brief pause to show completed state
      await new Promise((r) => setTimeout(r, 600));
      navigate(`/dashboard/${uploadRes.run_id}`);
    } catch (err: any) {
      setUploading(false);
      setAnalyzing(false);
      setError(err.response?.data?.detail || "Bir hata oluştu. Lütfen tekrar deneyin.");
    }
  };

  /* ── Agent Step Icon ─────────────────────────────── */

  const stepIcon = (status: string) => {
    if (status === "completed") return <CheckCircle2 className="h-4 w-4 text-emerald-400" />;
    if (status === "running") return <Loader2 className="h-4 w-4 text-brand-400 animate-spin" />;
    if (status === "failed") return <AlertCircle className="h-4 w-4 text-rose-400" />;
    return <div className="h-4 w-4 rounded-full border-2 border-slate-600" />;
  };

  /* ── Render ──────────────────────────────────────── */

  return (
    <div className="animate-fade-in">
      {/* Hero */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center gap-2 mb-4">
          <Sparkles className="h-5 w-5 text-amber-400" />
          <span className="text-sm font-medium text-amber-400">BTK Akademi Hackathon 2026</span>
        </div>
        <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight mb-4">
          <span className="bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
            Çok satmak yetmez;
          </span>
          <br />
          <span className="bg-gradient-to-r from-emerald-400 to-brand-400 bg-clip-text text-transparent">
            kâr ederek satmak gerekir.
          </span>
        </h1>
        <p className="text-lg text-slate-400 max-w-2xl mx-auto">
          Satış, iade, reklam ve yorum verilerinizi yükleyin.
          KârGuard AI zarar eden ürünlerinizi bulsun, nedenini açıklasın
          ve kâra döndürmek için aksiyon önersin.
        </p>
      </div>

      {/* Feature cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-10 max-w-3xl mx-auto">
        {[
          { icon: BarChart3, title: "SKU Kârlılık", desc: "Ürün bazlı gerçek kâr/zarar", color: "text-brand-400" },
          { icon: TrendingDown, title: "Zarar Tespiti", desc: "Çok satıp zarar eden ürünler", color: "text-rose-400" },
          { icon: ShieldCheck, title: "Aksiyon Planı", desc: "Onaylanabilir iyileştirme önerileri", color: "text-emerald-400" },
        ].map((f) => (
          <div key={f.title} className="glass-card p-4 text-center">
            <f.icon className={`h-7 w-7 mx-auto mb-2 ${f.color}`} />
            <p className="text-sm font-semibold text-white">{f.title}</p>
            <p className="text-xs text-slate-400 mt-0.5">{f.desc}</p>
          </div>
        ))}
      </div>

      {/* Upload Zone */}
      {!analyzing ? (
        <div className="max-w-2xl mx-auto">
          <div
            className={`dropzone p-10 text-center ${dragging ? "dropzone-active" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
          >
            <Upload className="h-12 w-12 mx-auto text-slate-500 mb-4" />
            <p className="text-base font-semibold text-slate-300 mb-1">
              CSV / Excel dosyalarını sürükle-bırak
            </p>
            <p className="text-sm text-slate-500 mb-4">
              orders.csv, returns.csv, products.csv, ads.csv, reviews.csv
            </p>
            <label className="btn-primary cursor-pointer">
              <FileSpreadsheet className="h-4 w-4" />
              Dosya Seç
              <input
                type="file"
                multiple
                accept={ACCEPTED}
                className="hidden"
                onChange={handleFileInput}
              />
            </label>
          </div>

          {/* File list */}
          {files.length > 0 && (
            <div className="mt-6 space-y-2">
              {files.map((f, i) => (
                <div
                  key={i}
                  className="glass-card flex items-center justify-between px-4 py-3 animate-slide-up"
                >
                  <div className="flex items-center gap-3">
                    <FileSpreadsheet className="h-4 w-4 text-brand-400" />
                    <span className="text-sm font-medium">{f.name}</span>
                    <span className="text-xs text-slate-500">
                      {(f.size / 1024).toFixed(1)} KB
                    </span>
                  </div>
                  <button
                    onClick={() => removeFile(i)}
                    className="text-slate-500 hover:text-rose-400 transition-colors"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}

              {error && (
                <div className="flex items-center gap-2 text-sm text-rose-400 mt-2">
                  <AlertCircle className="h-4 w-4" />
                  {error}
                </div>
              )}

              <button
                onClick={handleStart}
                disabled={uploading}
                className="btn-success w-full mt-4"
              >
                {uploading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Yükleniyor...
                  </>
                ) : (
                  <>
                    Kâr Analizini Başlat
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      ) : (
        /* Agent Progress */
        <div className="max-w-lg mx-auto glass-card p-8 animate-fade-in">
          <h2 className="text-lg font-bold mb-6 text-center">
            <Loader2 className="h-5 w-5 inline mr-2 animate-spin text-brand-400" />
            Agentic Pipeline Çalışıyor
          </h2>
          <div className="space-y-4">
            {agentSteps.map((step, i) => (
              <div
                key={i}
                className={`flex items-start gap-3 ${step.status === "running" ? "agent-step-running" : ""}`}
              >
                {stepIcon(step.status)}
                <div>
                  <p className="text-sm font-semibold">{step.step_name}</p>
                  <p className="text-xs text-slate-400">{step.message}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
