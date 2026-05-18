# Production Roadmap

This roadmap clarifies what remains after the current production-grade prototype.

## 1) Real MCP Transport
- Add stdio/SSE transport for external MCP servers.
- Implement process supervision and retry policies.

## 2) Data Layer Hardening
- Move from local SQLite to PostgreSQL.
- Introduce Alembic migrations and environment-specific schemas.

## 3) Auth and Tenant Isolation
- Add authentication and role-based access.
- Enforce tenant isolation in data access and traces.

## 4) Async Job Infrastructure
- Add queue workers and broker (Redis or equivalent).
- Isolate long-running analysis and retry failed jobs.

## 5) Marketplace Adapters
- Build adapters for real marketplace APIs.
- Add ingestion observability and schema drift handling.

## 6) Observability and Cost Tracking
- Add centralized logs, metrics, and distributed traces.
- Track model token usage and per-run cost.

## 7) Billing and Plans
- Add subscription plans and usage limits.
- Expose billing events and account-level controls.

## 8) Compliance Hardening
- Implement KVKK/GDPR workflows for retention and deletion.
- Add audit controls and policy enforcement.
