"""Insight Agent â€” Gemini-powered root cause analysis.

Takes financial data + reviews + returns â†’ produces structured RootCauseAnalysis.
This is the core AI differentiation of KÃ¢rGuard: why is this product losing money?
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, Field

from app.config import settings
from app.models.schemas import (
    SKUProfitability,
    RootCauseAnalysis,
    EvidenceItem,
    ActionCard,
    RiskLevel,
    ActionStatus,
)
from app.services.gemini_service import generate_structured, generate_text_with_tools

logger = logging.getLogger(__name__)


def _load_brand_voice_text() -> str:
    """Load brand voice guidelines from markdown file."""
    path = settings.BRAND_VOICE_PATH
    if not path.exists():
        logger.warning("brand_voice.md not found at %s", path)
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        logger.warning("brand_voice.md could not be read: %s", exc)
        return ""

# â”€â”€ Gemini Response Schemas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Separate models for Gemini structured output (simpler than full schemas)


class GeminiRootCause(BaseModel):
    """Schema for Gemini root cause analysis response."""
    main_cause: str = Field(description="ÃœrÃ¼nÃ¼n zarar etmesinin tek cÃ¼mlelik ana nedeni")
    explanation: str = Field(description="2-3 paragraf detaylÄ± aÃ§Ä±klama. Finansal veriler ve mÃ¼ÅŸteri yorumlarÄ±na referans verin.")
    review_problems: list[str] = Field(description="MÃ¼ÅŸteri yorumlarÄ±ndan tespit edilen en Ã¶nemli 3-5 problem")
    description_gaps: list[str] = Field(description="ÃœrÃ¼n aÃ§Ä±klamasÄ±nda eksik veya yanÄ±ltÄ±cÄ± olan 2-4 nokta")


class GeminiActionPlan(BaseModel):
    """Schema for Gemini action planning response."""
    actions: list[GeminiAction] = Field(description="Ã–nerilen 3-5 aksiyon")


class GeminiAction(BaseModel):
    """Single action recommendation from Gemini."""
    action_type: str = Field(description="Aksiyon tÃ¼rÃ¼: price_change | ad_budget | description_update | stock_pause | customer_reply")
    title: str = Field(description="KÄ±sa, aksiyona yÃ¶nelik baÅŸlÄ±k")
    reason: str = Field(description="Bu aksiyonun neden gerekli olduÄŸunun aÃ§Ä±klamasÄ±")
    expected_impact: str = Field(description="Beklenen etki: Ã¶r. 'Marj %15 iyileÅŸir', 'Ä°ade oranÄ± %20 dÃ¼ÅŸer'")
    risk_level: str = Field(description="Risk seviyesi: low | medium | high")


# Fix forward ref
GeminiActionPlan.model_rebuild()


# â”€â”€ System Instructions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

INSIGHT_SYSTEM = """Sen KÃ¢rGuard AI'Ä±n Insight Agent'Ä±sÄ±n. GÃ¶revin e-ticaret satÄ±cÄ±larÄ±nÄ±n zarar eden Ã¼rÃ¼nlerinin kÃ¶k nedenini analiz etmek.

Kurallar:
1. Sadece saÄŸlanan verilere dayalÄ± analiz yap. VarsayÄ±mda bulunma.
2. Finansal metrikleri (kÃ¢r/zarar, iade oranÄ±, reklam/ciro) doÄŸrudan referans ver.
3. MÃ¼ÅŸteri yorumlarÄ±ndaki kalÄ±plarÄ± (pattern) tespit et â€” beden, renk, kalite, paketleme vb.
4. Ä°ade nedenlerini grupla ve en sÄ±k tekrar edenleri vurgula.
5. ÃœrÃ¼n aÃ§Ä±klamasÄ±ndaki eksiklikleri somut ÅŸekilde belirt.
6. TÃ¼rkÃ§e yanÄ±t ver.
7. YanÄ±tÄ±n yapÄ±landÄ±rÄ±lmÄ±ÅŸ JSON olarak dÃ¶necek."""

ACTION_SYSTEM = """Sen KÃ¢rGuard AI'Ä±n Action Planning Agent'Ä±sÄ±n. GÃ¶revin zarar eden Ã¼rÃ¼nler iÃ§in uygulanabilir aksiyon Ã¶nerileri oluÅŸturmak.

Kurallar:
1. Her aksiyon somut ve Ã¶lÃ§Ã¼lebilir olmalÄ±.
2. Beklenen etkiyi tahmin et (Ã¶r. "iade oranÄ± %30 dÃ¼ÅŸebilir").
3. Risk seviyesini belirle: low (gÃ¼venli), medium (dikkatli uygulanmalÄ±), high (riskli).
4. Finansal verilere ve kÃ¶k neden analizine dayalÄ± Ã¶ner.
5. TÃ¼rkÃ§e yanÄ±t ver.
6. 3-5 arasÄ± aksiyon Ã¶ner, daha fazla deÄŸil."""


# â”€â”€ Data Collection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def _collect_evidence(sku: str, run_dir: Path) -> dict:
    """Collect reviews, returns, and product data for a SKU.
    Flow:
    1) Try Gemini function-calling with knowledge-mcp tools.
    2) Fallback to direct RAG service calls.
    3) Always enrich with CSV evidence.
    """
    evidence = {
        "reviews": [],
        "return_reasons": {},
        "product_description": "",
        "rag_reviews": [],
        "rag_descriptions": [],
        "rag_policies": [],
    }
    financial_hint = f"{sku} ?r?n problemi iade beden kalite ?ikayet"
    run_id = run_dir.name
    # 1) MCP <-> Gemini function-calling path
    try:
        from app.mcp_servers.knowledge_mcp_server import (
            retrieve_root_cause_evidence as mcp_retrieve_root_cause_evidence,
        )
        def retrieve_evidence_with_mcp(financial_summary: str) -> str:
            """Retrieve root cause evidence through knowledge-mcp.
            Args:
                financial_summary: Short summary used to guide semantic retrieval.
            Returns:
                JSON string with keys: reviews, product_descriptions, policies.
            """
            result = mcp_retrieve_root_cause_evidence(
                run_id=run_id,
                sku=sku,
                financial_summary=financial_summary,
                top_k_reviews=5,
                top_k_descriptions=2,
                top_k_policies=3,
            )
            return json.dumps(result.get("evidence", {}), ensure_ascii=False)
        tool_prompt = (
            f"SKU: {sku}\\n"
            f"Financial summary: {financial_hint}\\n\\n"
            "Use the retrieve_evidence_with_mcp tool first, then return ONLY JSON "
            "with keys: reviews, product_descriptions, policies."
        )
        tool_response_text = await generate_text_with_tools(
            prompt=tool_prompt,
            tools=[retrieve_evidence_with_mcp],
            system_instruction=(
                "You are an evidence retrieval assistant. "
                "Call the MCP tool and return strict JSON only."
            ),
            temperature=0.1,
            force_any_function=False,
        )
        start = tool_response_text.find("{")
        end = tool_response_text.rfind("}")
        if start != -1 and end != -1 and end > start:
            parsed = json.loads(tool_response_text[start:end + 1])
        else:
            parsed = {}
        for r in parsed.get("reviews", []):
            evidence["rag_reviews"].append({
                "rating": r.get("rating", 0),
                "comment": r.get("comment", ""),
                "score": r.get("score", 0.0),
            })
        for d in parsed.get("product_descriptions", []):
            evidence["rag_descriptions"].append({
                "name": d.get("name", ""),
                "description": d.get("description", ""),
                "score": d.get("score", 0.0),
            })
        for p in parsed.get("policies", []):
            evidence["rag_policies"].append({
                "section": p.get("section", ""),
                "subsection": p.get("subsection", ""),
                "text": p.get("text", ""),
                "score": p.get("score", 0.0),
            })
        logger.info(
            "MCP function-calling evidence topland? (%s): %s review, %s a??klama, %s politika",
            sku,
            len(evidence["rag_reviews"]),
            len(evidence["rag_descriptions"]),
            len(evidence["rag_policies"]),
        )
    except Exception as e:
        logger.warning(f"MCP function-calling ba?ar?s?z, do?rudan RAG fallback: {e}")
        # 2) Direct RAG fallback
        try:
            from app.services.qdrant_service import retrieve_root_cause_evidence
            rag_evidence = retrieve_root_cause_evidence(
                sku=sku,
                financial_summary=financial_hint,
            )
            for r in rag_evidence.get("reviews", []):
                evidence["rag_reviews"].append({
                    "rating": r.get("rating", 0),
                    "comment": r.get("comment", ""),
                    "score": r.get("score", 0.0),
                })
            for d in rag_evidence.get("product_descriptions", []):
                evidence["rag_descriptions"].append({
                    "name": d.get("name", ""),
                    "description": d.get("description", ""),
                    "score": d.get("score", 0.0),
                })
            for p in rag_evidence.get("policies", []):
                evidence["rag_policies"].append({
                    "section": p.get("section", ""),
                    "subsection": p.get("subsection", ""),
                    "text": p.get("text", ""),
                    "score": p.get("score", 0.0),
                })
        except Exception as rag_err:
            logger.warning(f"RAG fallback da ba?ar?s?z, CSV fallback aktif: {rag_err}")
    # CSV-based evidence (always collected for completeness)
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
            logger.warning(f"Reviews okunamad?: {e}")
    returns_path = run_dir / "returns.csv"
    if returns_path.exists():
        try:
            df = pd.read_csv(returns_path)
            sku_returns = df[df["sku"] == sku]
            if "return_reason" in sku_returns.columns:
                reason_counts = sku_returns["return_reason"].value_counts().to_dict()
                evidence["return_reasons"] = {str(k): int(v) for k, v in reason_counts.items()}
        except Exception as e:
            logger.warning(f"Returns okunamad?: {e}")
    products_path = run_dir / "products.csv"
    if products_path.exists():
        try:
            df = pd.read_csv(products_path)
            sku_product = df[df["sku"] == sku]
            if not sku_product.empty and "description" in sku_product.columns:
                evidence["product_description"] = str(sku_product.iloc[0]["description"])
        except Exception as e:
            logger.warning(f"Products okunamad?: {e}")
    return evidence
def _build_insight_prompt(product: SKUProfitability, evidence: dict) -> str:
    """Build the Gemini prompt for root cause analysis.

    Includes RAG evidence (semantic search results) when available.
    """

    # Reviews â€” prefer RAG (semantically ranked) over raw CSV
    rag_reviews = evidence.get("rag_reviews", [])
    csv_reviews = evidence.get("reviews", [])

    reviews_text = ""
    if rag_reviews:
        for i, r in enumerate(rag_reviews, 1):
            score_tag = f" [benzerlik: {r['score']:.2f}]" if r.get('score') else ""
            reviews_text += f"  {i}. â­{r['rating']}/5 â€” \"{r['comment']}\"{score_tag}\n"
        # Also add CSV reviews not in RAG results
        rag_comments = {r['comment'] for r in rag_reviews}
        extra_idx = len(rag_reviews) + 1
        for r in csv_reviews:
            if r['comment'] not in rag_comments:
                reviews_text += f"  {extra_idx}. â­{r['rating']}/5 â€” \"{r['comment']}\"\n"
                extra_idx += 1
    else:
        for i, r in enumerate(csv_reviews, 1):
            reviews_text += f"  {i}. â­{r['rating']}/5 â€” \"{r['comment']}\"\n"

    total_reviews = max(len(rag_reviews), len(csv_reviews))

    returns_text = ""
    for reason, count in evidence["return_reasons"].items():
        returns_text += f"  - {reason}: {count} adet\n"

    # Product description â€” prefer RAG detailed version
    rag_descs = evidence.get("rag_descriptions", [])
    desc_text = ""
    if rag_descs:
        for d in rag_descs:
            desc_text += f"  - {d['name']}: {d['description']}\n"
    elif evidence.get("product_description"):
        desc_text = f"  {evidence['product_description']}"

    # Policy evidence from RAG
    rag_policies = evidence.get("rag_policies", [])
    policy_text = ""
    if rag_policies:
        for p in rag_policies:
            section = p.get('section', '')
            subsection = p.get('subsection', '')
            text = p.get('text', '')[:300]
            policy_text += f"  - [{section} > {subsection}]: {text}\n"

    prompt = f"""AÅŸaÄŸÄ±daki e-ticaret Ã¼rÃ¼nÃ¼nÃ¼ analiz et. Bu Ã¼rÃ¼n Ã‡OK SATIYOR ama ZARAR EDÄ°YOR. KÃ¶k nedenini bul.

## ÃœrÃ¼n Bilgileri
- ÃœrÃ¼n: {product.product_name} ({product.sku})
- Kategori: {product.category}

## Finansal Veriler
- Toplam SatÄ±ÅŸ: {product.quantity_sold} adet
- BrÃ¼t Ciro: {product.gross_revenue:,.0f} TL
- ÃœrÃ¼n Maliyeti (COGS): {product.cogs:,.0f} TL
- Komisyon: {product.commission_cost:,.0f} TL
- Kargo: {product.shipping_cost:,.0f} TL
- Reklam HarcamasÄ±: {product.ad_spend:,.0f} TL
- Ä°ade SayÄ±sÄ±: {product.return_count} adet (iade oranÄ±: %{product.return_rate:.1f})
- Ä°ade Bedeli: {product.refund_amount:,.0f} TL
- Ä°ade Kargo: {product.return_shipping_cost:,.0f} TL
- **NET KÃ‚R: {product.net_profit:,.0f} TL** (marj: %{product.profit_margin:.1f})
- Reklam/Ciro: %{product.ad_to_revenue_ratio:.1f}
- Risk Skoru: {product.risk_score:.0f}/100

## MÃ¼ÅŸteri YorumlarÄ± ({total_reviews} adet)
{reviews_text if reviews_text else "  Yorum bulunamadÄ±."}

## Ä°ade Nedenleri
{returns_text if returns_text else "  Ä°ade verisi bulunamadÄ±."}

## ÃœrÃ¼n AÃ§Ä±klamasÄ±
{desc_text if desc_text else "  AÃ§Ä±klama bulunamadÄ±."}"""

    # Add policy section only if RAG policies are available
    if policy_text:
        prompt += f"""\n\n## Ä°lgili Pazar Yeri PolitikalarÄ± (RAG)
{policy_text}"""

    prompt += "\n\nBu verilere dayanarak kÃ¶k neden analizi yap."
    return prompt


def _build_action_prompt(
    product: SKUProfitability,
    root_cause: RootCauseAnalysis,
) -> str:
    """Build the Gemini prompt for action planning."""
    brand_voice = _load_brand_voice_text()
    prompt = f"""AÅŸaÄŸÄ±daki zarar eden Ã¼rÃ¼n iÃ§in aksiyon planÄ± oluÅŸtur.

## ÃœrÃ¼n: {product.product_name} ({product.sku})

## Finansal Ã–zet
- Net KÃ¢r: {product.net_profit:,.0f} TL
- Ä°ade OranÄ±: %{product.return_rate:.1f}
- Reklam/Ciro: %{product.ad_to_revenue_ratio:.1f}
- Risk Skoru: {product.risk_score:.0f}/100

## KÃ¶k Neden Analizi
- Ana Neden: {root_cause.main_cause}
- AÃ§Ä±klama: {root_cause.explanation}
- Yorumlardaki Problemler: {', '.join(root_cause.review_problems)}
- AÃ§Ä±klama Eksiklikleri: {', '.join(root_cause.description_gaps)}
- Ä°ade Nedenleri: {root_cause.return_reasons}

Bu analiz Ä±ÅŸÄ±ÄŸÄ±nda somut, uygulanabilir aksiyonlar Ã¶ner. Her aksiyonun beklenen etkisini tahmin et."""
    if brand_voice:
        prompt += (
            "\n\n## Brand Voice Kurallari\n"
            "Aksiyonlarin baslik ve gerekce metinlerini asagidaki marka sesi ile uyumlu yaz:\n"
            f"{brand_voice}\n"
        )
    return prompt


# â”€â”€ Main Agent Functions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def analyze_root_cause(
    product: SKUProfitability,
    run_dir: Path,
) -> RootCauseAnalysis:
    """Run Gemini root cause analysis for a single SKU."""

    evidence = await _collect_evidence(product.sku, run_dir)
    prompt = _build_insight_prompt(product, evidence)

    try:
        result = await generate_structured(
            prompt=prompt,
            response_schema=GeminiRootCause,
            system_instruction=INSIGHT_SYSTEM,
            temperature=0.3,
        )

        # Build evidence items â€” combine RAG + CSV sources
        evidence_items: list[EvidenceItem] = []

        # RAG review evidence (semantically ranked)
        for r in evidence.get("rag_reviews", []):
            evidence_items.append(EvidenceItem(
                source="rag_review",
                text=r["comment"],
                relevance_score=r.get("score", 0.5),
            ))

        # CSV review evidence (low-rating reviews)
        rag_comments = {r["comment"] for r in evidence.get("rag_reviews", [])}
        for r in evidence["reviews"]:
            if r["rating"] <= 3 and r["comment"] not in rag_comments:
                evidence_items.append(EvidenceItem(
                    source="review",
                    text=r["comment"],
                    relevance_score=1.0 - (r["rating"] / 5.0),
                ))

        # RAG policy evidence
        for p in evidence.get("rag_policies", []):
            section = p.get("section", "")
            subsection = p.get("subsection", "")
            evidence_items.append(EvidenceItem(
                source="policy",
                text=f"[{section} > {subsection}] {p.get('text', '')[:200]}",
                relevance_score=p.get("score", 0.5),
            ))

        # RAG product description evidence
        for d in evidence.get("rag_descriptions", []):
            evidence_items.append(EvidenceItem(
                source="product_description",
                text=f"{d.get('name', '')}: {d.get('description', '')[:200]}",
                relevance_score=d.get("score", 0.5),
            ))

        return RootCauseAnalysis(
            sku=product.sku,
            product_name=product.product_name,
            main_cause=result.get("main_cause", "Analiz yapÄ±lamadÄ±"),
            explanation=result.get("explanation", ""),
            evidence=evidence_items,
            review_problems=result.get("review_problems", []),
            return_reasons=evidence["return_reasons"],
            description_gaps=result.get("description_gaps", []),
        )

    except Exception as e:
        logger.error(f"Root cause analizi baÅŸarÄ±sÄ±z ({product.sku}): {e}")
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
        logger.error(f"Action plan oluÅŸturulamadÄ± ({product.sku}): {e}")
        # Fallback: rule-based actions
        return _fallback_actions(product)


# â”€â”€ Fallback (No Gemini / API failure) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _fallback_root_cause(
    product: SKUProfitability,
    evidence: dict,
) -> RootCauseAnalysis:
    """Rule-based fallback when Gemini is unavailable."""

    causes = []
    if product.return_rate > 15:
        causes.append(f"YÃ¼ksek iade oranÄ± (%{product.return_rate:.1f})")
    if product.ad_to_revenue_ratio > 10:
        causes.append(f"YÃ¼ksek reklam harcamasÄ± (cironun %{product.ad_to_revenue_ratio:.1f}'i)")
    if product.profit_margin < -10:
        causes.append(f"Negatif kÃ¢r marjÄ± (%{product.profit_margin:.1f})")

    main = " ve ".join(causes) if causes else "Ã‡oklu maliyet baskÄ±sÄ±"

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
        explanation=f"ÃœrÃ¼n {product.quantity_sold} adet satÄ±ÅŸ yapmasÄ±na raÄŸmen {product.net_profit:,.0f} TL zarar ediyor. "
                    f"(Gemini API baÄŸlantÄ±sÄ± kurulamadÄ± â€” kural tabanlÄ± analiz.)",
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
            title=f"{product.product_name} fiyatÄ±nÄ± artÄ±r",
            reason=f"Net zarar: {product.net_profit:,.0f} TL",
            expected_impact="Marj iyileÅŸmesi",
            risk_level=RiskLevel.MEDIUM,
        ),
        ActionCard(
            sku=product.sku,
            action_type="ad_budget",
            title=f"{product.product_name} reklam bÃ¼tÃ§esini azalt",
            reason=f"Reklam/ciro: %{product.ad_to_revenue_ratio:.1f}",
            expected_impact="Maliyet dÃ¼ÅŸÃ¼ÅŸÃ¼",
            risk_level=RiskLevel.LOW,
        ),
    ]
    if product.return_rate > 15:
        cards.append(ActionCard(
            sku=product.sku,
            action_type="description_update",
            title=f"{product.product_name} Ã¼rÃ¼n aÃ§Ä±klamasÄ±nÄ± gÃ¼ncelle",
            reason=f"Ä°ade oranÄ±: %{product.return_rate:.1f}",
            expected_impact="Ä°ade oranÄ± dÃ¼ÅŸÃ¼ÅŸÃ¼",
            risk_level=RiskLevel.LOW,
        ))
    return cards

