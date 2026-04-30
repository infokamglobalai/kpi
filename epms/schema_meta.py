"""Portable schema introspection (SQLite vs PostgreSQL)."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection


def table_columns(conn: Connection, dialect: str, table: str) -> set[str]:
    allowed = {"users", "scorecards", "audit_logs", "review_cycles", "kpi_registry_overrides"}
    if table not in allowed:
        raise ValueError(f"Unexpected table: {table}")
    if dialect == "sqlite":
        res = conn.execute(text(f"PRAGMA table_info({table})"))
        return {row[1] for row in res.fetchall()}
    res = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :t
            """
        ),
        {"t": table},
    )
    return {row[0] for row in res.fetchall()}


def insert_scorecard_returning_id(conn: Connection, dialect: str, params: dict) -> int:
    if dialect == "postgresql":
        row = conn.execute(
            text(
                """
                INSERT INTO scorecards (
                    created_at, review_date, employee_name, department, role,
                    final_score, rating, kpi_json, breakdown_json, created_by,
                    review_cycle, status, self_comment, manager_comment, evidence_url
                ) VALUES (
                    :created_at, :review_date, :employee_name, :department, :role,
                    :final_score, :rating, :kpi_json, :breakdown_json, :created_by,
                    :review_cycle, :status, :self_comment, :manager_comment, :evidence_url
                )
                RETURNING id
                """
            ),
            params,
        ).fetchone()
        return int(row[0])
    conn.execute(
        text(
            """
            INSERT INTO scorecards (
                created_at, review_date, employee_name, department, role,
                final_score, rating, kpi_json, breakdown_json, created_by,
                review_cycle, status, self_comment, manager_comment, evidence_url
            ) VALUES (
                :created_at, :review_date, :employee_name, :department, :role,
                :final_score, :rating, :kpi_json, :breakdown_json, :created_by,
                :review_cycle, :status, :self_comment, :manager_comment, :evidence_url
            )
            """
        ),
        params,
    )
    rid = conn.execute(text("SELECT last_insert_rowid()")).scalar()
    return int(rid)
