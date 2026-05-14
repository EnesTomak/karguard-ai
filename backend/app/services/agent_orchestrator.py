"""Agent orchestrator - 5-step agentic pipeline."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from app.models.schemas import (
    ActionCard,
    AgentStepResponse,
    AnalysisRunResponse,
    AnalysisStatus,
    RootCauseAnalysis,
)
from app.services.finance_engine import FinanceEngine
from app.services.storage_service import (
    get_root_cause as db_get_root_cause,
    upsert_kpis,
    upsert_products,
    upsert_root_causes,
)

logger = logging.getLogger(__name__)

# In-memory root cause cache: run_id -> {sku: RootCauseAnalysis}
_root_cause_cache: dict[str, dict[str, RootCauseAnalysis]] = {}


def get_root_cause(run_id: str, sku: str) -> RootCauseAnalysis | None:
    """Retrieve cached root cause analysis with DB fallback."""
    cached = _root_cause_cache.get(run_id, {}).get(sku)
    if cached is not None:
        return cached
    return db_get_root_cause(run_id, sku)


async def run_pipeline(run_id: str, run_dir: Path) -> AnalysisRunResponse:
    """Execute the full analysis pipeline."""
    steps: list[AgentStepResponse] = []
    now = lambda: datetime.now().isoformat()

    # Step 1: Data validation
    steps.append(
        AgentStepResponse(
            step_name="Data Quality Agent",
            status="running",
            message="Yüklenen dosyalar doğrulanıyor...",
            timestamp=now(),
        )
    )

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

    # Step 2: Finance calculations
    steps.append(
        AgentStepResponse(
            step_name="Profitability Agent",
            status="running",
            message="SKU bazlı kârlılık hesaplanıyor...",
            timestamp=now(),
        )
    )
    engine = FinanceEngine.from_directory(run_dir)
    engine.cache(run_id)
    upsert_kpis(run_id, engine.kpis)
    upsert_products(run_id, engine.get_all_products())
    steps[-1].status = "completed"
    steps[-1].message = f"{len(engine.profitability)} ürünün kârlılığı hesaplandı."

    # Step 3: Loss makers
    steps.append(
        AgentStepResponse(
            step_name="Loss Maker Agent",
            status="running",
            message="Zarar eden ürünler tespit ediliyor...",
            timestamp=now(),
        )
    )
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

    # Step 3.5: RAG indexing
    steps.append(
        AgentStepResponse(
            step_name="RAG Knowledge Agent",
            status="running",
            message="Veriler vektörleştiriliyor (Qdrant RAG)...",
            timestamp=now(),
        )
    )
    try:
        from app.services.qdrant_service import index_all

        rag_results = index_all(run_dir)
        if rag_results.get("skipped"):
            steps[-1].status = "completed"
            steps[-1].message = "RAG index zaten mevcut, atlandı."
        else:
            total = rag_results["reviews"] + rag_results["products"] + rag_results["policies"]
            steps[-1].status = "completed"
            steps[-1].message = (
                f"{total} vektör oluşturuldu "
                f"(reviews: {rag_results['reviews']}, "
                f"products: {rag_results['products']}, "
                f"policies: {rag_results['policies']})"
            )
    except Exception as exc:
        logger.warning("RAG indexing başarısız (fallback devam eder): %s", exc)
        steps[-1].status = "completed"
        steps[-1].message = f"RAG indexing atlandı: {str(exc)[:100]}"

    # Step 4: Root cause analysis
    steps.append(
        AgentStepResponse(
            step_name="Insight Agent",
            status="running",
            message="Gemini ile kök neden analizi yapılıyor...",
            timestamp=now(),
        )
    )

    root_causes: dict[str, RootCauseAnalysis] = {}
    if loss_makers:
        from app.services.insight_agent import analyze_root_cause

        for lm in loss_makers:
            try:
                rc = await analyze_root_cause(lm, run_dir)
                root_causes[lm.sku] = rc
                logger.info("Root cause tamamlandı: %s", lm.sku)
                await asyncio.sleep(3)
            except Exception as exc:
                logger.error("Root cause hatası (%s): %s", lm.sku, exc)
                root_causes[lm.sku] = RootCauseAnalysis(
                    sku=lm.sku,
                    product_name=lm.product_name,
                    main_cause="Analiz başarısız oldu",
                    explanation=str(exc),
                )

        _root_cause_cache[run_id] = root_causes
        upsert_root_causes(run_id, root_causes)
        steps[-1].status = "completed"
        steps[-1].message = f"{len(root_causes)} ürünün kök neden analizi tamamlandı."
    else:
        steps[-1].status = "completed"
        steps[-1].message = "Zarar eden ürün yok, kök neden analizi atlandı."

    # Step 5: Action planning
    steps.append(
        AgentStepResponse(
            step_name="Action Agent",
            status="running",
            message="Gemini ile aksiyon planı oluşturuluyor...",
            timestamp=now(),
        )
    )
    from app.api.actions import register_actions
    from app.services.insight_agent import _fallback_actions, generate_action_plan

    all_actions: list[ActionCard] = []
    for lm in loss_makers:
        rc = root_causes.get(lm.sku)
        if rc is None:
            continue
        try:
            actions = await generate_action_plan(lm, rc)
            all_actions.extend(actions)
        except Exception as exc:
            logger.error("Action plan hatası (%s): %s", lm.sku, exc)
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

