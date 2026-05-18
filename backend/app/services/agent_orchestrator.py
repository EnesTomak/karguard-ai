"""Agent orchestrator - multi-step analysis pipeline."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.models.schemas import (
    ActionCard,
    AgentStepResponse,
    AnalysisRunResponse,
    AnalysisStatus,
    RootCauseAnalysis,
)
from app.mcp_client.audit import get_tool_traces
from app.services.guardrail_service import (
    build_guardrail_report,
    verify_evidence_refs,
    verify_loss_maker_skus,
)
from app.services.action_registry import clear_actions_for_run, register_actions
from app.services.finance_engine import FinanceEngine
from app.services.storage_service import (
    delete_root_causes,
    get_root_cause as db_get_root_cause,
    upsert_guardrail_report,
    upsert_kpis,
    upsert_products,
    upsert_root_causes,
)

logger = logging.getLogger(__name__)

# In-memory root cause cache: run_id -> {sku: RootCauseAnalysis}
_root_cause_cache: dict[str, dict[str, RootCauseAnalysis]] = {}

ProgressHook = Callable[[list[AgentStepResponse], AnalysisStatus], Awaitable[None]]


def get_root_cause(run_id: str, sku: str) -> RootCauseAnalysis | None:
    """Retrieve cached root cause analysis with DB fallback."""
    cached = _root_cause_cache.get(run_id, {}).get(sku)
    if cached is not None:
        return cached
    return db_get_root_cause(run_id, sku)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _tool_trace_ids_for_run(run_id: str) -> list[str]:
    traces = get_tool_traces(run_id)
    return [trace.trace_id for trace in traces]


def _aggregate_evidence_check(root_causes: dict[str, RootCauseAnalysis]) -> dict[str, object]:
    if not root_causes:
        return {
            "name": "evidence_reference_validation",
            "status": "degraded",
            "message": "Evidence dogrulama icin root cause kaydi bulunamadi.",
            "metadata": {
                "evidence_refs_valid": False,
                "validated_skus": [],
            },
        }

    checks = [
        verify_evidence_refs(root_cause=root_cause, evidence_items=root_cause.evidence)
        for root_cause in root_causes.values()
    ]
    failed = [check for check in checks if check["status"] == "failed"]
    degraded = [check for check in checks if check["status"] == "degraded"]
    valid_count = sum(
        1
        for check in checks
        if isinstance(check.get("metadata"), dict) and bool(check["metadata"].get("evidence_refs_valid"))
    )

    if failed:
        status = "failed"
        message = f"{len(failed)} SKU icin evidence referanslari dogrulanamadi."
        evidence_refs_valid = False
    elif degraded:
        status = "degraded"
        message = f"{len(degraded)} SKU icin evidence dogrulamasi eksik veri nedeniyle kisitli."
        evidence_refs_valid = False
    else:
        status = "passed"
        message = f"{len(checks)} SKU icin evidence referanslari dogrulandi."
        evidence_refs_valid = True

    return {
        "name": "evidence_reference_validation",
        "status": status,
        "message": message,
        "metadata": {
            "evidence_refs_valid": evidence_refs_valid,
            "validated_skus": sorted(root_causes.keys()),
            "valid_count": valid_count,
            "total_count": len(checks),
        },
    }


def _read_upload_table(run_dir: Path, name: str) -> pd.DataFrame:
    csv = run_dir / f"{name}.csv"
    xlsx = run_dir / f"{name}.xlsx"
    xls = run_dir / f"{name}.xls"
    if csv.exists():
        return pd.read_csv(csv)
    if xlsx.exists():
        return pd.read_excel(xlsx)
    if xls.exists():
        return pd.read_excel(xls)
    return pd.DataFrame()


def _validate_required_columns(run_dir: Path) -> list[str]:
    required_columns = {
        "orders": {"sku", "quantity", "unit_price"},
        "products": {"sku", "name", "unit_cost"},
        "returns": {"sku", "return_reason"},
        "ads": {"sku", "spend"},
        "reviews": {"sku", "rating", "comment"},
    }
    problems: list[str] = []
    for table_name, expected in required_columns.items():
        table = _read_upload_table(run_dir, table_name)
        if table.empty:
            problems.append(f"{table_name}: empty or unreadable")
            continue
        missing = sorted(expected - set(table.columns))
        if missing:
            problems.append(f"{table_name}: missing columns -> {', '.join(missing)}")
    return problems


async def _emit_progress(
    progress_hook: ProgressHook | None,
    steps: list[AgentStepResponse],
    status: AnalysisStatus = AnalysisStatus.RUNNING,
) -> None:
    if progress_hook is None:
        return
    # Use deep copies to avoid accidental mutation while persisting.
    snapshot = [step.model_copy(deep=True) for step in steps]
    await progress_hook(snapshot, status)


async def run_pipeline(
    run_id: str,
    run_dir: Path,
    progress_hook: ProgressHook | None = None,
) -> AnalysisRunResponse:
    """Execute the full analysis pipeline."""
    steps: list[AgentStepResponse] = []

    # Step 1: Data validation
    steps.append(
        AgentStepResponse(
            step_name="Data Quality Agent",
            status="running",
            message="Yuklenen dosyalar dogrulaniyor...",
            timestamp=_now_iso(),
        )
    )
    await _emit_progress(progress_hook, steps)

    schema_problems = _validate_required_columns(run_dir)
    if schema_problems:
        steps[-1].status = "failed"
        steps[-1].message = "Semaya uymayan veri: " + " | ".join(schema_problems)
        await _emit_progress(progress_hook, steps, AnalysisStatus.FAILED)
        return AnalysisRunResponse(
            run_id=run_id,
            status=AnalysisStatus.FAILED,
            created_at=_now_iso(),
            agent_steps=steps,
        )

    steps[-1].status = "completed"
    steps[-1].message = "Dosya ve kolon dogrulamasi tamamlandi."
    await _emit_progress(progress_hook, steps)

    # Reset run-scoped artifacts before recomputing to avoid stale data on reruns.
    _root_cause_cache.pop(run_id, None)
    delete_root_causes(run_id)
    clear_actions_for_run(run_id)

    # Step 2: Finance calculations
    steps.append(
        AgentStepResponse(
            step_name="Profitability Agent",
            status="running",
            message="SKU bazli karlilik hesaplanıyor...",
            timestamp=_now_iso(),
        )
    )
    await _emit_progress(progress_hook, steps)

    engine = FinanceEngine.from_directory(run_dir)
    engine.cache(run_id)
    upsert_kpis(run_id, engine.kpis)
    upsert_products(run_id, engine.get_all_products())

    steps[-1].status = "completed"
    steps[-1].message = f"{len(engine.profitability)} urunun karliligi hesaplandi."
    await _emit_progress(progress_hook, steps)

    # Step 3: Loss makers
    steps.append(
        AgentStepResponse(
            step_name="Loss Maker Agent",
            status="running",
            message="Zarar eden urunler tespit ediliyor...",
            timestamp=_now_iso(),
        )
    )
    await _emit_progress(progress_hook, steps)

    from app.services.insight_agent import agentic_detect_loss_makers
    
    agentic_result = await agentic_detect_loss_makers(run_id)
    agentic_skus = agentic_result.skus
    
    # Verify the agentic result with deterministic engine as fallback/guard
    deterministic_loss_makers = engine.get_loss_makers()
    deterministic_skus = {p.sku for p in deterministic_loss_makers}
    
    # Only keep SKUs that the engine confirms are actually losing money
    verified_skus = [sku for sku in agentic_skus if sku in deterministic_skus]
    
    used_guardrail_fallback = False
    if not verified_skus:
        # Fallback to deterministic if the agent completely failed
        logger.warning(f"Agentic loss maker detection yielded no valid SKUs. Falling back to deterministic engine.")
        used_guardrail_fallback = True
        loss_makers = deterministic_loss_makers
    else:
        # Use the agent's verified SKUs
        logger.info(
            "Gemini -> MCP Gateway -> finance-mcp.detect_loss_maker_skus completed with %s verified SKUs.",
            len(verified_skus),
        )
        loss_makers = [product for sku in verified_skus if (product := engine.get_product(sku)) is not None]

    loss_maker_guardrail_check = verify_loss_maker_skus(
        agent_skus=agentic_skus,
        deterministic_skus=deterministic_skus,
    )
    upsert_guardrail_report(
        run_id=run_id,
        report=build_guardrail_report(
            loss_maker_check=loss_maker_guardrail_check,
            tool_trace_ids=_tool_trace_ids_for_run(run_id),
        ),
    )

    steps[-1].status = "completed"
    if agentic_result.used_fallback:
        steps[-1].message = "MCP tool çağrısı başarısız oldu, deterministic fallback kullanıldı."
    elif used_guardrail_fallback:
        steps[-1].message = (
            "Gemini -> MCP Gateway çağrısı tamamlandı ancak guardrail doğrulamasından geçen SKU bulunamadı; "
            "deterministic fallback kullanıldı."
        )
    elif loss_makers:
        worst = max(loss_makers, key=lambda p: abs(p.net_profit))
        steps[-1].message = (
            "Gemini -> MCP Gateway -> finance-mcp.detect_loss_maker_skus çağrısı tamamlandı. "
            f"{len(loss_makers)} zarar eden urun bulundu. "
            f"En riskli: {worst.product_name} ({worst.net_profit:,.0f} TL zarar)"
        )
    else:
        steps[-1].message = "Zarar eden urun bulunamadi."
    await _emit_progress(progress_hook, steps)

    # Step 3.5: RAG indexing
    steps.append(
        AgentStepResponse(
            step_name="RAG Knowledge Agent",
            status="running",
            message="Veriler RAG index'e aktariliyor...",
            timestamp=_now_iso(),
        )
    )
    await _emit_progress(progress_hook, steps)

    try:
        from app.services.qdrant_service import index_all

        rag_results = index_all(run_dir)
        if rag_results.get("skipped"):
            steps[-1].status = "completed"
            steps[-1].message = "RAG index zaten mevcut, atlandi."
        else:
            total = rag_results["reviews"] + rag_results["products"] + rag_results["policies"]
            steps[-1].status = "completed"
            steps[-1].message = (
                f"{total} vektor olusturuldu "
                f"(reviews: {rag_results['reviews']}, "
                f"products: {rag_results['products']}, "
                f"policies: {rag_results['policies']})"
            )
    except Exception as exc:
        logger.warning("RAG indexing basarisiz, fallback devam eder: %s", exc)
        steps[-1].status = "completed"
        steps[-1].message = f"RAG indexing atlandi: {str(exc)[:120]}"
    await _emit_progress(progress_hook, steps)

    # Step 4: Root cause analysis
    steps.append(
        AgentStepResponse(
            step_name="Insight Agent",
            status="running",
            message="Gemini ile kok neden analizi yapiliyor...",
            timestamp=_now_iso(),
        )
    )
    await _emit_progress(progress_hook, steps)

    root_causes: dict[str, RootCauseAnalysis] = {}
    if loss_makers:
        from app.config import settings
        from app.services.insight_agent import analyze_root_cause

        prioritized_loss_makers = sorted(
            loss_makers,
            key=lambda p: abs(p.net_profit),
            reverse=True,
        )
        max_ai_skus = max(1, settings.MAX_AI_SKUS_PER_RUN)
        ai_targets = prioritized_loss_makers[:max_ai_skus]
        skipped_count = max(0, len(prioritized_loss_makers) - len(ai_targets))

        for lm in ai_targets:
            try:
                root_causes[lm.sku] = await analyze_root_cause(lm, run_dir)
            except Exception as exc:
                logger.error("Root cause hatasi (%s): %s", lm.sku, exc)
                root_causes[lm.sku] = RootCauseAnalysis(
                    sku=lm.sku,
                    product_name=lm.product_name,
                    main_cause="Analiz basarisiz oldu",
                    explanation=str(exc),
                )

        _root_cause_cache[run_id] = root_causes
        upsert_root_causes(run_id, root_causes)
        steps[-1].status = "completed"
        steps[-1].message = (
            f"{len(root_causes)} urunun kok neden analizi tamamlandi."
            + (f" {skipped_count} urun hizli demo modu nedeniyle atlandi." if skipped_count else "")
        )
    else:
        steps[-1].status = "completed"
        steps[-1].message = "Zarar eden urun yok, kok neden analizi atlandi."

    evidence_guardrail_check = _aggregate_evidence_check(root_causes)
    upsert_guardrail_report(
        run_id=run_id,
        report=build_guardrail_report(
            loss_maker_check=loss_maker_guardrail_check,
            evidence_check=evidence_guardrail_check,
            tool_trace_ids=_tool_trace_ids_for_run(run_id),
        ),
    )
    await _emit_progress(progress_hook, steps)

    # Step 5: Action planning
    steps.append(
        AgentStepResponse(
            step_name="Action Agent",
            status="running",
            message="Aksiyon plani olusturuluyor...",
            timestamp=_now_iso(),
        )
    )
    await _emit_progress(progress_hook, steps)

    from app.services.insight_agent import _fallback_actions, generate_action_plan

    all_actions: list[ActionCard] = []
    for lm in loss_makers:
        rc = root_causes.get(lm.sku)
        if rc is None:
            continue
        try:
            all_actions.extend(await generate_action_plan(lm, rc))
        except Exception as exc:
            logger.error("Action plan hatasi (%s): %s", lm.sku, exc)
            all_actions.extend(_fallback_actions(lm))

    register_actions(all_actions, run_id)
    steps[-1].status = "completed"
    steps[-1].message = f"{len(all_actions)} aksiyon karti olusturuldu."

    result = AnalysisRunResponse(
        run_id=run_id,
        status=AnalysisStatus.COMPLETED,
        created_at=_now_iso(),
        agent_steps=steps,
    )
    await _emit_progress(progress_hook, steps, AnalysisStatus.COMPLETED)
    return result
