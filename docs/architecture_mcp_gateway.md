# MCP Gateway Architecture (P0)

## Runtime Flow
```mermaid
flowchart LR
    U["User Upload + Analyze"] --> O["Agent Orchestrator"]
    O --> G["Gemini Function Calling"]
    G --> W["Gateway Wrapper Tool"]
    W --> C["MCPClientGateway.call_tool()"]
    C --> R["Tool Registry"]
    R --> F["finance-mcp.detect_loss_maker_skus"]
    F --> E["Deterministic FinanceEngine"]
    E --> T["Tool Result"]
    T --> C
    C --> A["Trace Audit: Memory + SQLite"]
    T --> V["Guardrail Validation"]
    V --> O
    A --> API["GET /api/traces/run_id"]
    API --> UI["Upload + Dashboard Trace Panels"]
```

## Design Guarantees
- Agent/business code does not call finance tools directly.
- Centralized tool invocation API:
  - `MCPClientGateway.call_tool(...)`
- Tool call metadata is always traced:
  - `status`, `latency_ms`, `arguments`, `result`, `error_message`
- Guardrail remains deterministic:
  - Only SKUs validated by `FinanceEngine.get_loss_makers()` are accepted.

## P0 Notes
- P0 uses in-process registry routing instead of stdio transport.
- Gateway interface is production-oriented and transport-agnostic.
- Stdio/SSE transport can be introduced later without changing agent API.
