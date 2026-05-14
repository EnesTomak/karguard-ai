import { Outlet, Link } from "react-router-dom";
import { Shield } from "lucide-react";

export default function Layout() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* ── Navbar ──────────────────────────────────── */}
      <header className="sticky top-0 z-50 border-b border-slate-700/40 bg-slate-900/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-2.5 group">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl gradient-brand shadow-lg shadow-blue-600/20 transition-transform duration-200 group-hover:scale-105">
              <Shield className="h-5 w-5 text-white" />
            </div>
            <div className="flex flex-col">
              <span className="text-lg font-bold tracking-tight text-white leading-tight">
                KârGuard <span className="text-brand-400">AI</span>
              </span>
              <span className="text-[10px] font-medium text-slate-500 uppercase tracking-widest leading-none">
                Agentic ProfitOps
              </span>
            </div>
          </Link>

          <div className="flex items-center gap-3">
            <span className="badge-info">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
              Gemini + RAG + MCP
            </span>
          </div>
        </div>
      </header>

      {/* ── Main Content ───────────────────────────── */}
      <main className="flex-1">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 py-8">
          <Outlet />
        </div>
      </main>

      {/* ── Footer ─────────────────────────────────── */}
      <footer className="border-t border-slate-800/50 py-4">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 flex items-center justify-between text-xs text-slate-500">
          <span>© 2026 KârGuard AI — BTK Akademi Hackathon</span>
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            Powered by Gemini
          </span>
        </div>
      </footer>
    </div>
  );
}
