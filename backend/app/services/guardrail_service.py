"""Guardrail validation utilities for agentic pipeline outputs."""

from __future__ import annotations

import math
from typing import Any, Iterable, Literal

from app.models.schemas import GuardrailCheck, GuardrailReport

CheckStatus = Literal["passed", "failed", "degraded"]


def _normalize_skus(items: Iterable[object]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in items:
        sku = str(raw).strip()
        if not sku or sku in seen:
            continue
        seen.add(sku)
        ordered.append(sku)
    return ordered


def _summarize_status(statuses: Iterable[CheckStatus]) -> CheckStatus:
    statuses_set = set(statuses)
    if "failed" in statuses_set:
        return "failed"
    if "degraded" in statuses_set:
        return "degraded"
    return "passed"


def verify_loss_maker_skus(agent_skus: list[str], deterministic_skus: set[str]) -> dict[str, Any]:
    """Verify agent-selected SKUs against deterministic loss-maker set."""
    normalized_agent_skus = _normalize_skus(agent_skus)
    deterministic_sorted = sorted(deterministic_skus)
    verified_skus = [sku for sku in normalized_agent_skus if sku in deterministic_skus]
    invalid_skus = [sku for sku in normalized_agent_skus if sku not in deterministic_skus]

    if not deterministic_skus and not normalized_agent_skus:
        status: CheckStatus = "passed"
        message = "Deterministic engine zarar eden SKU bulmadi; agent sonucu da bos."
    elif not normalized_agent_skus and deterministic_skus:
        status = "degraded"
        message = "Agent SKU listesi bos dondu; deterministic fallback gerekli."
    elif verified_skus and not invalid_skus:
        status = "passed"
        message = f"{len(verified_skus)} SKU deterministic guardrail dogrulamasindan gecti."
    elif verified_skus and invalid_skus:
        status = "degraded"
        message = (
            f"{len(verified_skus)} SKU dogrulandi, {len(invalid_skus)} SKU deterministic guardrail tarafindan reddedildi."
        )
    else:
        status = "failed"
        message = "Agent SKU listesinde deterministic guardrail'den gecen SKU bulunamadi."

    return {
        "name": "loss_maker_sku_validation",
        "status": status,
        "message": message,
        "metadata": {
            "agent_skus": normalized_agent_skus,
            "deterministic_skus": deterministic_sorted,
            "verified_skus": verified_skus,
            "invalid_skus": invalid_skus,
            "fallback_required": status in {"degraded", "failed"},
        },
    }


def verify_evidence_refs(root_cause: Any, evidence_items: Any) -> dict[str, Any]:
    """Validate root-cause reference usage against available evidence items."""
    if root_cause is None:
        return {
            "name": "evidence_reference_validation",
            "status": "degraded",
            "message": "Root cause kaydi bulunamadi.",
            "metadata": {"evidence_refs_valid": False, "missing_refs": [], "available_refs": []},
        }

    evidence_list = list(evidence_items or [])
    available_refs = {
        str(getattr(item, "reference_id", "")).strip()
        for item in evidence_list
        if str(getattr(item, "reference_id", "")).strip()
    }
    supporting_refs = _normalize_skus(getattr(root_cause, "main_cause_supporting_refs", []) or [])

    if not evidence_list:
        status: CheckStatus = "degraded"
        evidence_refs_valid = False
        missing_refs = supporting_refs
        message = "Root cause icin evidence item bulunamadi."
    elif supporting_refs:
        missing_refs = [ref for ref in supporting_refs if ref not in available_refs]
        if missing_refs:
            status = "failed"
            evidence_refs_valid = False
            message = "Root cause referanslari evidence listesinde bulunamadi."
        else:
            status = "passed"
            evidence_refs_valid = True
            message = "Root cause referanslari evidence listesi ile eslesiyor."
    else:
        missing_refs = []
        status = "passed"
        evidence_refs_valid = True
        message = "Evidence item mevcut; explicit supporting ref verilmemis."

    return {
        "name": "evidence_reference_validation",
        "status": status,
        "message": message,
        "metadata": {
            "evidence_refs_valid": evidence_refs_valid,
            "missing_refs": missing_refs,
            "available_refs": sorted(available_refs),
            "supporting_refs": supporting_refs,
            "evidence_count": len(evidence_list),
        },
    }


def verify_simulation_result(simulation_result: Any) -> dict[str, Any]:
    """Validate simulation result payload and mark whether it is verifiable."""
    if simulation_result is None:
        return {
            "name": "simulation_result_validation",
            "status": "degraded",
            "message": "Bu run icin simulation sonucu bulunamadi.",
            "metadata": {"simulation_verified": False},
        }

    if hasattr(simulation_result, "model_dump"):
        payload = simulation_result.model_dump()
    elif isinstance(simulation_result, dict):
        payload = simulation_result
    else:
        payload = {}

    candidate = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    numeric_fields = ("current_profit", "simulated_profit", "profit_delta", "new_margin")
    is_valid = all(
        isinstance(candidate.get(field), (int, float)) and math.isfinite(float(candidate.get(field)))
        for field in numeric_fields
    )

    if is_valid:
        status: CheckStatus = "passed"
        simulation_verified = True
        message = "Simulation sonucu deterministik formatta dogrulandi."
    else:
        status = "failed"
        simulation_verified = False
        message = "Simulation sonucu beklenen alanlari icermiyor."

    return {
        "name": "simulation_result_validation",
        "status": status,
        "message": message,
        "metadata": {
            "simulation_verified": simulation_verified,
            "scenario_label": str(candidate.get("scenario_label", "")),
        },
    }


def _to_guardrail_check(raw_check: dict[str, Any]) -> GuardrailCheck:
    return GuardrailCheck(
        name=str(raw_check.get("name", "unknown_check")),
        status=raw_check.get("status", "degraded"),
        message=str(raw_check.get("message", "")),
        metadata=raw_check.get("metadata", {}) if isinstance(raw_check.get("metadata", {}), dict) else {},
    )


def build_guardrail_report(
    *,
    loss_maker_check: dict[str, Any] | None = None,
    evidence_check: dict[str, Any] | None = None,
    simulation_check: dict[str, Any] | None = None,
    verified_by: str = "deterministic_finance_engine",
    tool_trace_ids: list[str] | None = None,
) -> GuardrailReport:
    """Build normalized guardrail report from individual validation checks."""
    checks: list[GuardrailCheck] = []
    for candidate in (loss_maker_check, evidence_check, simulation_check):
        if isinstance(candidate, dict):
            checks.append(_to_guardrail_check(candidate))

    status = _summarize_status(check.status for check in checks) if checks else "degraded"

    evidence_refs_valid = bool(
        evidence_check and isinstance(evidence_check.get("metadata"), dict) and evidence_check["metadata"].get("evidence_refs_valid")
    )
    simulation_verified = bool(
        simulation_check
        and isinstance(simulation_check.get("metadata"), dict)
        and simulation_check["metadata"].get("simulation_verified")
    )

    dedup_trace_ids = list(dict.fromkeys((tool_trace_ids or [])))

    return GuardrailReport(
        status=status,
        verified_by=verified_by,
        checks=checks,
        evidence_refs_valid=evidence_refs_valid,
        simulation_verified=simulation_verified,
        tool_trace_ids=dedup_trace_ids,
    )
