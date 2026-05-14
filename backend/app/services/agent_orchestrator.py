"""Agent Orchestrator — 5-step agentic pipeline.

Steps:
1. Data Validation
2. Profitability Analysis (Deterministic)
3. Loss Maker Detection (Deterministic)
4. Gemini + Evidence Root Cause Analysis (AI)
5. Gemini Action Planning (AI)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from app.models.schemas import (
    AnalysisRunResponse,
    AnalysisStatus,
    AgentStepResponse,
    ActionCard,
    RiskLevel,
    RootCauseAnalysis,
)
from app.services.finance_engine import FinanceEngine

logger = logging.getLogger(__name__)

# In-memory root cause cache: run_id -> {sku: RootCauseAnalysis}
_root_cause_cache: dict[str, dict[str, RootCauseAnalysis]] = {}


def get_root_cause(run_id: str, sku: str) -> RootCauseAnalysis | None:
    """Retrieve cached root cause analysis."""
    return _root_cause_cache.get(run_id, {}).get(sku)


async def run_pipeline(run_id: str, run_dir: Path) -> AnalysisRunResponse:
    """Execute the full agentic analysis pipeline."""

    steps: list[AgentStepResponse] = []
    now = lambda: datetime.now().isoformat()

    # ── Step 1: Data Validation ────────────────────────
    steps.append(AgentStepResponse(
        step_name="Data Quality Agent",
        status="running",
        message="Yüklenen dosyalar doğrulanıyor...",
        timestamp=now(),
    ))

    required_files = ["orders.csv", "products.csv"]
    missing = [f for f in required_files if not (run_dir / f).exists()]
    if missing:
        steps[-1].status = "failed"
        steps[-1].message = f"Eksik dosyalar: {', '.join(missing)}"
        return AnalysisRunResponse(
            run_id=run_id,
            status=AnalysisStatus.FAILED,
            created_at=now(),
            agent_steps=steps,
        )

    steps[-1].status = "completed"
    steps[-1].message = "Tüm dosyalar doğrulandı."

    # ── Step 2: Profitability Analysis ─────────────────
    steps.append(AgentStepResponse(
        step_name="Profitability Agent",
        status="running",
        message="SKU bazlı kârlılık hesaplanıyor...",
        timestamp=now(),
    ))

    engine = FinanceEngine.from_directory(run_dir)
    engine.cache(run_id)

    steps[-1].status = "completed"
    steps[-1].message = f"{len(engine.profitability)} ürünün kârlılığı hesaplandı."

    # ── Step 3: Loss Maker Detection ───────────────────
    steps.append(AgentStepResponse(
        step_name="Loss Maker Agent",
        status="running",
        message="Zarar eden ürünler tespit ediliyor...",
        timestamp=now(),
    ))

    loss_makers = engine.get_loss_makers()
    steps[-1].status = "completed"
    if loss_makers:
        worst = max(loss_makers, key=lambda p: abs(p.net_profit))
        steps[-1].message = (
            f"{len(loss_makers)} zarar eden ürün bulundu. "
            f"En riskli: {worst.product_name} ({worst.net_profit:,.0f} TL zarar)"
        )
    else:
        steps[-1].message = "Zarar eden ürün bulunamadı."

    # ── Step 4: Root Cause Analysis (Gemini) ───────────
    steps.append(AgentStepResponse(
        step_name="Insight Agent",
        status="running",
        message="Gemini ile kök neden analizi yapılıyor...",
        timestamp=now(),
    ))

    root_causes: dict[str, RootCauseAnalysis] = {}

    if loss_makers:
        from app.services.insight_agent import analyze_root_cause

        for lm in loss_makers:
            try:
                rc = await analyze_root_cause(lm, run_dir)
                root_causes[lm.sku] = rc
                logger.info(f"Root cause tamamlandı: {lm.sku} → {rc.main_cause[:60]}...")
                # Delay between calls to respect rate limits
                await asyncio.sleep(3)
            except Exception as e:
                logger.error(f"Root cause hatası ({lm.sku}): {e}")
                # Store empty analysis
                root_causes[lm.sku] = RootCauseAnalysis(
                    sku=lm.sku,
                    product_name=lm.product_name,
                    main_cause="Analiz başarısız oldu",
                    explanation=str(e),
                )

        _root_cause_cache[run_id] = root_causes
        steps[-1].status = "completed"
        steps[-1].message = f"{len(root_causes)} ürünün kök neden analizi tamamlandı."
    else:
        steps[-1].status = "completed"
        steps[-1].message = "Zarar eden ürün yok, kök neden analizi atlandı."

    # ── Step 5: Action Planning (Gemini) ───────────────
    steps.append(AgentStepResponse(
        step_name="Action Agent",
        status="running",
        message="Gemini ile aksiyon planı oluşturuluyor...",
        timestamp=now(),
    ))

    from app.services.insight_agent import generate_action_plan
    from app.api.actions import register_actions

    all_actions: list[ActionCard] = []

    for lm in loss_makers:
        rc = root_causes.get(lm.sku)
        if rc:
            try:
                actions = await generate_action_plan(lm, rc)
                all_actions.extend(actions)
                logger.info(f"Action plan tamamlandı: {lm.sku} → {len(actions)} aksiyon")
            except Exception as e:
                logger.error(f"Action plan hatası ({lm.sku}): {e}")
                # Fallback rule-based actions
                from app.services.insight_agent import _fallback_actions
                all_actions.extend(_fallback_actions(lm))

    register_actions(all_actions, run_id)

    steps[-1].status = "completed"
    steps[-1].message = f"{len(all_actions)} aksiyon kartı oluşturuldu."

    return AnalysisRunResponse(
        run_id=run_id,
        status=AnalysisStatus.COMPLETED,
        created_at=now(),
        agent_steps=steps,
    )
