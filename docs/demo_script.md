# Demo Script (MCP Gateway Proof)

## Goal
Show that KârGuard AI is not a chatbot-only demo and that tool execution is auditable:

```text
Gemini -> MCP Gateway -> finance-mcp.detect_loss_maker_skus -> Tool Result -> Guardrail -> UI Trace
```

## 1) Upload
1. Open upload screen.
2. Upload required datasets:
   - `orders.csv`
   - `returns.csv`
   - `products.csv`
   - `ads.csv`
   - `reviews.csv`
3. Start analysis.

## 2) Live Agent Step + Trace
1. While analysis runs, show `Loss Maker Agent`.
2. Open the `MCP Tool Trace` panel on Upload page.
3. Narrate:
   - Gemini requested tool
   - Route via `MCP Gateway -> finance-mcp.detect_loss_maker_skus`
   - Status and latency

## 3) API Proof
1. Call:
   ```bash
   GET /api/traces/{run_id}
   ```
2. Show trace entries with:
   - `server`
   - `tool_name`
   - `status`
   - `latency_ms`
   - `arguments` / `result`

## 4) Guardrail Proof
1. Explain guardrail behavior:
   - Agent output SKUs are validated against deterministic `FinanceEngine.get_loss_makers()`.
   - Invalid SKUs are rejected.
2. Explain fallback behavior:
   - If MCP/tool or function-calling fails, deterministic fallback continues analysis.
   - Trace includes `status=error` for failures.

## 5) Dashboard Proof
1. Navigate to dashboard.
2. Show `MCP Tool Trace` card.
3. Reconfirm visible chain text:
   - `Gemini -> MCP Gateway -> finance-mcp -> Tool Result`

## 6) Closing Statement
Use this concise summary:

> Gemini is orchestrating tool usage, but deterministic finance logic remains the source of truth.  
> MCP Gateway centralizes tool calls, and every call is traceable from API to UI.

