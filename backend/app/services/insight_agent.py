"""Insight Agent — Gemini-powered root cause analysis.

Takes financial data + reviews + returns → produces structured RootCauseAnalysis.
This is the core AI differentiation of KârGuard: why is this product losing money?
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, Field

from app.models.schemas import (
    SKUProfitability,
    RootCauseAnalysis,
    EvidenceItem,
    ActionCard,
    RiskLevel,
    ActionStatus,
)
from app.services.gemini_service import generate_structured

logger = logging.getLogger(__name__)

# ── Gemini Response Schemas ───────────────────────────
# Separate models for Gemini structured output (simpler than full schemas)


class GeminiRootCause(BaseModel):
    """Schema for Gemini root cause analysis response."""
    main_cause: str = Field(description="Ürünün zarar etmesinin tek cümlelik ana nedeni")
    explanation: str = Field(description="2-3 paragraf detaylı açıklama. Finansal veriler ve müşteri yorumlarına referans verin.")
    review_problems: list[str] = Field(description="Müşteri yorumlarından tespit edilen en önemli 3-5 problem")
    description_gaps: list[str] = Field(description="Ürün açıklamasında eksik veya yanıltıcı olan 2-4 nokta")


class GeminiActionPlan(BaseModel):
    """Schema for Gemini action planning response."""
    actions: list[GeminiAction] = Field(description="Önerilen 3-5 aksiyon")


class GeminiAction(BaseModel):
    """Single action recommendation from Gemini."""
    action_type: str = Field(description="Aksiyon türü: price_change | ad_budget | description_update | stock_pause | customer_reply")
    title: str = Field(description="Kısa, aksiyona yönelik başlık")
    reason: str = Field(description="Bu aksiyonun neden gerekli olduğunun açıklaması")
    expected_impact: str = Field(description="Beklenen etki: ör. 'Marj %15 iyileşir', 'İade oranı %20 düşer'")
    risk_level: str = Field(description="Risk seviyesi: low | medium | high")


# Fix forward ref
GeminiActionPlan.model_rebuild()


# ── System Instructions ───────────────────────────────

INSIGHT_SYSTEM = """Sen KârGuard AI'ın Insight Agent'ısın. Görevin e-ticaret satıcılarının zarar eden ürünlerinin kök nedenini analiz etmek.

Kurallar:
1. Sadece sağlanan verilere dayalı analiz yap. Varsayımda bulunma.
2. Finansal metrikleri (kâr/zarar, iade oranı, reklam/ciro) doğrudan referans ver.
3. Müşteri yorumlarındaki kalıpları (pattern) tespit et — beden, renk, kalite, paketleme vb.
4. İade nedenlerini grupla ve en sık tekrar edenleri vurgula.
5. Ürün açıklamasındaki eksiklikleri somut şekilde belirt.
6. Türkçe yanıt ver.
7. Yanıtın yapılandırılmış JSON olarak dönecek."""

ACTION_SYSTEM = """Sen KârGuard AI'ın Action Planning Agent'ısın. Görevin zarar eden ürünler için uygulanabilir aksiyon önerileri oluşturmak.

Kurallar:
1. Her aksiyon somut ve ölçülebilir olmalı.
2. Beklenen etkiyi tahmin et (ör. "iade oranı %30 düşebilir").
3. Risk seviyesini belirle: low (güvenli), medium (dikkatli uygulanmalı), high (riskli).
4. Finansal verilere ve kök neden analizine dayalı öner.
5. Türkçe yanıt ver.
6. 3-5 arası aksiyon öner, daha fazla değil."""


# ── Data Collection ───────────────────────────────────

def _collect_evidence(sku: str, run_dir: Path) -> dict:
    """Collect reviews, returns, and product data for a SKU."""
    evidence = {
        "reviews": [],
        "return_reasons": {},
        "product_description": "",
    }

    # Reviews
    reviews_path = run_dir / "reviews.csv"
    if reviews_path.exists():
        try:
            df = pd.read_csv(reviews_path)
            sku_reviews = df[df["sku"] == sku]
            for _, row in sku_reviews.iterrows():
                evidence["reviews"].append({
                    "rating": int(row.get("rating", 0)),
                    "comment": str(row.get("comment", "")),
                })
        except Exception as e:
            logger.warning(f"Reviews okunamadı: {e}")

    # Returns
    returns_path = run_dir / "returns.csv"
    if returns_path.exists():
        try:
            df = pd.read_csv(returns_path)
            sku_returns = df[df["sku"] == sku]
            if "return_reason" in sku_returns.columns:
                reason_counts = sku_returns["return_reason"].value_counts().to_dict()
                evidence["return_reasons"] = {str(k): int(v) for k, v in reason_counts.items()}
        except Exception as e:
            logger.warning(f"Returns okunamadı: {e}")

    # Product description
    products_path = run_dir / "products.csv"
    if products_path.exists():
        try:
            df = pd.read_csv(products_path)
            sku_product = df[df["sku"] == sku]
            if not sku_product.empty and "description" in sku_product.columns:
                evidence["product_description"] = str(sku_product.iloc[0]["description"])
        except Exception as e:
            logger.warning(f"Products okunamadı: {e}")

    return evidence


def _build_insight_prompt(product: SKUProfitability, evidence: dict) -> str:
    """Build the Gemini prompt for root cause analysis."""

    reviews_text = ""
    for i, r in enumerate(evidence["reviews"], 1):
        reviews_text += f"  {i}. ⭐{r['rating']}/5 — \"{r['comment']}\"\n"

    returns_text = ""
    for reason, count in evidence["return_reasons"].items():
        returns_text += f"  - {reason}: {count} adet\n"

    return f"""Aşağıdaki e-ticaret ürününü analiz et. Bu ürün ÇOK SATIYOR ama ZARAR EDİYOR. Kök nedenini bul.

## Ürün Bilgileri
- Ürün: {product.product_name} ({product.sku})
- Kategori: {product.category}

## Finansal Veriler
- Toplam Satış: {product.quantity_sold} adet
- Brüt Ciro: {product.gross_revenue:,.0f} TL
- Ürün Maliyeti (COGS): {product.cogs:,.0f} TL
- Komisyon: {product.commission_cost:,.0f} TL
- Kargo: {product.shipping_cost:,.0f} TL
- Reklam Harcaması: {product.ad_spend:,.0f} TL
- İade Sayısı: {product.return_count} adet (iade oranı: %{product.return_rate:.1f})
- İade Bedeli: {product.refund_amount:,.0f} TL
- İade Kargo: {product.return_shipping_cost:,.0f} TL
- **NET KÂR: {product.net_profit:,.0f} TL** (marj: %{product.profit_margin:.1f})
- Reklam/Ciro: %{product.ad_to_revenue_ratio:.1f}
- Risk Skoru: {product.risk_score:.0f}/100

## Müşteri Yorumları ({len(evidence['reviews'])} adet)
{reviews_text if reviews_text else "  Yorum bulunamadı."}

## İade Nedenleri
{returns_text if returns_text else "  İade verisi bulunamadı."}

## Ürün Açıklaması
{evidence['product_description'] if evidence['product_description'] else "  Açıklama bulunamadı."}

Bu verilere dayanarak kök neden analizi yap."""


def _build_action_prompt(
    product: SKUProfitability,
    root_cause: RootCauseAnalysis,
) -> str:
    """Build the Gemini prompt for action planning."""

    return f"""Aşağıdaki zarar eden ürün için aksiyon planı oluştur.

## Ürün: {product.product_name} ({product.sku})

## Finansal Özet
- Net Kâr: {product.net_profit:,.0f} TL
- İade Oranı: %{product.return_rate:.1f}
- Reklam/Ciro: %{product.ad_to_revenue_ratio:.1f}
- Risk Skoru: {product.risk_score:.0f}/100

## Kök Neden Analizi
- Ana Neden: {root_cause.main_cause}
- Açıklama: {root_cause.explanation}
- Yorumlardaki Problemler: {', '.join(root_cause.review_problems)}
- Açıklama Eksiklikleri: {', '.join(root_cause.description_gaps)}
- İade Nedenleri: {root_cause.return_reasons}

Bu analiz ışığında somut, uygulanabilir aksiyonlar öner. Her aksiyonun beklenen etkisini tahmin et."""


# ── Main Agent Functions ──────────────────────────────

async def analyze_root_cause(
    product: SKUProfitability,
    run_dir: Path,
) -> RootCauseAnalysis:
    """Run Gemini root cause analysis for a single SKU."""

    evidence = _collect_evidence(product.sku, run_dir)
    prompt = _build_insight_prompt(product, evidence)

    try:
        result = await generate_structured(
            prompt=prompt,
            response_schema=GeminiRootCause,
            system_instruction=INSIGHT_SYSTEM,
            temperature=0.3,
        )

        # Build evidence items from reviews
        evidence_items: list[EvidenceItem] = []
        for r in evidence["reviews"]:
            if r["rating"] <= 3:
                evidence_items.append(EvidenceItem(
                    source="review",
                    text=r["comment"],
                    relevance_score=1.0 - (r["rating"] / 5.0),
                ))

        return RootCauseAnalysis(
            sku=product.sku,
            product_name=product.product_name,
            main_cause=result.get("main_cause", "Analiz yapılamadı"),
            explanation=result.get("explanation", ""),
            evidence=evidence_items,
            review_problems=result.get("review_problems", []),
            return_reasons=evidence["return_reasons"],
            description_gaps=result.get("description_gaps", []),
        )

    except Exception as e:
        logger.error(f"Root cause analizi başarısız ({product.sku}): {e}")
        # Fallback: return evidence-only analysis without Gemini
        return _fallback_root_cause(product, evidence)


async def generate_action_plan(
    product: SKUProfitability,
    root_cause: RootCauseAnalysis,
) -> list[ActionCard]:
    """Generate Gemini-powered action cards for a product."""

    prompt = _build_action_prompt(product, root_cause)

    try:
        result = await generate_structured(
            prompt=prompt,
            response_schema=GeminiActionPlan,
            system_instruction=ACTION_SYSTEM,
            temperature=0.4,
        )

        cards: list[ActionCard] = []
        for action_data in result.get("actions", []):
            risk_map = {"low": RiskLevel.LOW, "medium": RiskLevel.MEDIUM, "high": RiskLevel.HIGH}
            cards.append(ActionCard(
                sku=product.sku,
                action_type=action_data.get("action_type", "description_update"),
                title=action_data.get("title", ""),
                reason=action_data.get("reason", ""),
                expected_impact=action_data.get("expected_impact", ""),
                risk_level=risk_map.get(action_data.get("risk_level", "low"), RiskLevel.LOW),
                status=ActionStatus.PENDING,
            ))

        return cards

    except Exception as e:
        logger.error(f"Action plan oluşturulamadı ({product.sku}): {e}")
        # Fallback: rule-based actions
        return _fallback_actions(product)


# ── Fallback (No Gemini / API failure) ────────────────

def _fallback_root_cause(
    product: SKUProfitability,
    evidence: dict,
) -> RootCauseAnalysis:
    """Rule-based fallback when Gemini is unavailable."""

    causes = []
    if product.return_rate > 15:
        causes.append(f"Yüksek iade oranı (%{product.return_rate:.1f})")
    if product.ad_to_revenue_ratio > 10:
        causes.append(f"Yüksek reklam harcaması (cironun %{product.ad_to_revenue_ratio:.1f}'i)")
    if product.profit_margin < -10:
        causes.append(f"Negatif kâr marjı (%{product.profit_margin:.1f})")

    main = " ve ".join(causes) if causes else "Çoklu maliyet baskısı"

    evidence_items = []
    for r in evidence.get("reviews", []):
        if r["rating"] <= 3:
            evidence_items.append(EvidenceItem(
                source="review",
                text=r["comment"],
                relevance_score=1.0 - (r["rating"] / 5.0),
            ))

    return RootCauseAnalysis(
        sku=product.sku,
        product_name=product.product_name,
        main_cause=main,
        explanation=f"Ürün {product.quantity_sold} adet satış yapmasına rağmen {product.net_profit:,.0f} TL zarar ediyor. "
                    f"(Gemini API bağlantısı kurulamadı — kural tabanlı analiz.)",
        evidence=evidence_items,
        review_problems=[],
        return_reasons=evidence.get("return_reasons", {}),
        description_gaps=[],
    )


def _fallback_actions(product: SKUProfitability) -> list[ActionCard]:
    """Rule-based fallback actions when Gemini is unavailable."""
    cards = [
        ActionCard(
            sku=product.sku,
            action_type="price_change",
            title=f"{product.product_name} fiyatını artır",
            reason=f"Net zarar: {product.net_profit:,.0f} TL",
            expected_impact="Marj iyileşmesi",
            risk_level=RiskLevel.MEDIUM,
        ),
        ActionCard(
            sku=product.sku,
            action_type="ad_budget",
            title=f"{product.product_name} reklam bütçesini azalt",
            reason=f"Reklam/ciro: %{product.ad_to_revenue_ratio:.1f}",
            expected_impact="Maliyet düşüşü",
            risk_level=RiskLevel.LOW,
        ),
    ]
    if product.return_rate > 15:
        cards.append(ActionCard(
            sku=product.sku,
            action_type="description_update",
            title=f"{product.product_name} ürün açıklamasını güncelle",
            reason=f"İade oranı: %{product.return_rate:.1f}",
            expected_impact="İade oranı düşüşü",
            risk_level=RiskLevel.LOW,
        ))
    return cards
