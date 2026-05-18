# KârGuard AI

Agentic ProfitOps platform for marketplace sellers.

## What It Does
- Ingests seller data (`orders`, `returns`, `products`, `ads`, `reviews`)
- Computes deterministic SKU-level profitability and risk
- Uses Gemini for agentic reasoning while keeping financial math deterministic
- Runs MCP-routed finance tools through a central gateway
- Records tool traces for auditability and demo proof

## Verified P0 MCP Flow
```text
Gemini -> MCP Gateway -> finance-mcp.detect_loss_maker_skus -> Tool Result -> Guardrail -> UI Trace
```

## Key Components
- Backend API: FastAPI
- Deterministic finance core: `FinanceEngine`
- MCP gateway: `backend/app/mcp_client/gateway.py`
- MCP finance tools: `backend/app/mcp_servers/finance_mcp_server.py`
- Tool trace API: `GET /api/traces/{run_id}`
- Frontend trace panels: Upload page + Dashboard page

## Quick Start
### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Test Commands
### Backend
```bash
cd backend
python -m pytest
```

### Frontend
```bash
cd frontend
npm run build
npm run test:run
```

## Demo Guide
- See [Demo Script](docs/demo_script.md)
- See [MCP Gateway Architecture](docs/architecture_mcp_gateway.md)

