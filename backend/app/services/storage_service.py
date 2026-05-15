"""SQLite storage service for persistent local state.

Stores:
- analysis runs
- KPI snapshots
- product snapshots
- root cause snapshots
- action cards
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.config import settings
from app.models.schemas import (
    ActionCard,
    ActionStatus,
    AnalysisRunResponse,
    DashboardKPIs,
    DashboardResponse,
    RootCauseAnalysis,
    SKUProfitability,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(settings.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create SQLite tables if they do not exist."""
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS analysis_runs (
                run_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                response_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kpi_snapshots (
                run_id TEXT PRIMARY KEY,
                kpis_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS product_snapshots (
                run_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                product_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (run_id, sku),
                FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS root_cause_snapshots (
                run_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                root_cause_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (run_id, sku),
                FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS action_cards (
                action_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                status TEXT NOT NULL,
                action_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_action_cards_run_id ON action_cards(run_id);
            CREATE INDEX IF NOT EXISTS idx_action_cards_run_sku ON action_cards(run_id, sku);
            """
        )


def upsert_analysis_run(result: AnalysisRunResponse) -> None:
    now = _utc_now_iso()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO analysis_runs (run_id, status, created_at, response_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                status=excluded.status,
                created_at=excluded.created_at,
                response_json=excluded.response_json,
                updated_at=excluded.updated_at
            """,
            (
                result.run_id,
                result.status.value,
                result.created_at,
                result.model_dump_json(),
                now,
            ),
        )


def get_analysis_run(run_id: str) -> AnalysisRunResponse | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT response_json FROM analysis_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    return AnalysisRunResponse.model_validate_json(row["response_json"])


def upsert_kpis(run_id: str, kpis: DashboardKPIs) -> None:
    now = _utc_now_iso()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO kpi_snapshots (run_id, kpis_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                kpis_json=excluded.kpis_json,
                updated_at=excluded.updated_at
            """,
            (run_id, kpis.model_dump_json(), now),
        )


def upsert_products(run_id: str, products: list[SKUProfitability]) -> None:
    now = _utc_now_iso()
    with _get_conn() as conn:
        conn.execute("DELETE FROM product_snapshots WHERE run_id = ?", (run_id,))
        conn.executemany(
            """
            INSERT INTO product_snapshots (run_id, sku, product_json, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                (run_id, p.sku, p.model_dump_json(), now)
                for p in products
            ],
        )


def get_products(run_id: str) -> list[SKUProfitability]:
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT product_json
            FROM product_snapshots
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchall()
    products = [SKUProfitability.model_validate_json(r["product_json"]) for r in rows]
    return sorted(products, key=lambda p: p.risk_score, reverse=True)


def get_product(run_id: str, sku: str) -> SKUProfitability | None:
    with _get_conn() as conn:
        row = conn.execute(
            """
            SELECT product_json
            FROM product_snapshots
            WHERE run_id = ? AND sku = ?
            """,
            (run_id, sku),
        ).fetchone()
    if row is None:
        return None
    return SKUProfitability.model_validate_json(row["product_json"])


def get_dashboard(run_id: str) -> DashboardResponse | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT kpis_json FROM kpi_snapshots WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    if row is None:
        return None

    kpis = DashboardKPIs.model_validate_json(row["kpis_json"])
    products = get_products(run_id)
    loss_makers = [p for p in products if p.net_profit < 0]
    return DashboardResponse(
        run_id=run_id,
        kpis=kpis,
        products=products,
        loss_makers=loss_makers,
    )


def upsert_root_causes(run_id: str, items: dict[str, RootCauseAnalysis]) -> None:
    now = _utc_now_iso()
    with _get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO root_cause_snapshots (run_id, sku, root_cause_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(run_id, sku) DO UPDATE SET
                root_cause_json=excluded.root_cause_json,
                updated_at=excluded.updated_at
            """,
            [
                (run_id, sku, root_cause.model_dump_json(), now)
                for sku, root_cause in items.items()
            ],
        )


def delete_root_causes(run_id: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "DELETE FROM root_cause_snapshots WHERE run_id = ?",
            (run_id,),
        )


def get_root_cause(run_id: str, sku: str) -> RootCauseAnalysis | None:
    with _get_conn() as conn:
        row = conn.execute(
            """
            SELECT root_cause_json
            FROM root_cause_snapshots
            WHERE run_id = ? AND sku = ?
            """,
            (run_id, sku),
        ).fetchone()
    if row is None:
        return None
    return RootCauseAnalysis.model_validate_json(row["root_cause_json"])


def upsert_actions(run_id: str, actions: list[ActionCard]) -> None:
    now = _utc_now_iso()
    with _get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO action_cards (action_id, run_id, sku, status, action_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(action_id) DO UPDATE SET
                run_id=excluded.run_id,
                sku=excluded.sku,
                status=excluded.status,
                action_json=excluded.action_json,
                updated_at=excluded.updated_at
            """,
            [
                (
                    a.action_id,
                    run_id,
                    a.sku,
                    a.status.value,
                    a.model_dump_json(),
                    now,
                )
                for a in actions
            ],
        )


def delete_actions(run_id: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "DELETE FROM action_cards WHERE run_id = ?",
            (run_id,),
        )


def get_action(action_id: str) -> tuple[str, ActionCard] | None:
    with _get_conn() as conn:
        row = conn.execute(
            """
            SELECT run_id, action_json
            FROM action_cards
            WHERE action_id = ?
            """,
            (action_id,),
        ).fetchone()
    if row is None:
        return None
    return row["run_id"], ActionCard.model_validate_json(row["action_json"])


def list_actions(run_id: str) -> list[ActionCard]:
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT action_json
            FROM action_cards
            WHERE run_id = ?
            ORDER BY updated_at DESC
            """,
            (run_id,),
        ).fetchall()
    return [ActionCard.model_validate_json(r["action_json"]) for r in rows]


def list_actions_for_sku(run_id: str, sku: str) -> list[ActionCard]:
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT action_json
            FROM action_cards
            WHERE run_id = ? AND sku = ?
            ORDER BY updated_at DESC
            """,
            (run_id, sku),
        ).fetchall()
    return [ActionCard.model_validate_json(r["action_json"]) for r in rows]


def update_action_status(action_id: str, status: ActionStatus) -> ActionCard | None:
    entry = get_action(action_id)
    if entry is None:
        return None
    run_id, card = entry
    card.status = status
    upsert_actions(run_id, [card])
    return card

