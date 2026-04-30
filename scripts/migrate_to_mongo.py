from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

from epms.db_adapter import build_database_config
from epms.mongo import get_db


def _load_source_rows(sqlalchemy_conn):
    users = sqlalchemy_conn.execute(
        text(
            """
            SELECT username, role, password_hash, password_salt, manager_username, department, is_active, created_at
            FROM users
            """
        )
    ).mappings().all()

    scorecards = sqlalchemy_conn.execute(
        text(
            """
            SELECT
                id, created_at, review_date, employee_name, department, role,
                final_score, rating, kpi_json, breakdown_json, created_by,
                review_cycle, status, self_comment, manager_comment, evidence_url
            FROM scorecards
            """
        )
    ).mappings().all()

    review_cycles = sqlalchemy_conn.execute(
        text("SELECT cycle_name, is_closed, updated_at FROM review_cycles")
    ).mappings().all()

    audit_logs = sqlalchemy_conn.execute(
        text(
            """
            SELECT created_at, actor, action, entity_type, entity_id, details
            FROM audit_logs
            """
        )
    ).mappings().all()

    overrides = sqlalchemy_conn.execute(
        text(
            """
            SELECT department, role, metric, current_value, priority, frequency, status_override, updated_at
            FROM kpi_registry_overrides
            """
        )
    ).mappings().all()

    return users, scorecards, review_cycles, audit_logs, overrides


def main() -> None:
    load_dotenv()

    # Source (SQLite by default, or Postgres if EPMS_DATABASE_URL is set)
    db_path = Path(os.getenv("EPMS_DB_PATH", "epms.db"))
    cfg = build_database_config(db_path)

    from sqlalchemy import create_engine

    engine = create_engine(cfg.database_url, pool_pre_ping=True)

    mongo_db = get_db()

    with engine.connect() as conn:
        users, scorecards, review_cycles, audit_logs, overrides = _load_source_rows(conn)

    # Users (upsert by username)
    for u in users:
        mongo_db["users"].update_one(
            {"username": str(u["username"]).strip().lower()},
            {
                "$set": {
                    "role": u["role"],
                    "password_hash": u["password_hash"],
                    "password_salt": u["password_salt"],
                    "manager_username": u.get("manager_username"),
                    "department": u.get("department"),
                    "is_active": int(u.get("is_active") or 0),
                    "created_at": u.get("created_at"),
                },
                "$setOnInsert": {"username": str(u["username"]).strip().lower()},
            },
            upsert=True,
        )

    # Review cycles (upsert by cycle_name)
    for rc in review_cycles:
        mongo_db["review_cycles"].update_one(
            {"cycle_name": rc["cycle_name"]},
            {
                "$set": {
                    "is_closed": int(rc.get("is_closed") or 0),
                    "updated_at": rc.get("updated_at"),
                },
                "$setOnInsert": {"cycle_name": rc["cycle_name"]},
            },
            upsert=True,
        )

    # KPI registry overrides (upsert by compound key)
    for o in overrides:
        mongo_db["kpi_registry_overrides"].update_one(
            {"department": o["department"], "role": o["role"], "metric": o["metric"]},
            {
                "$set": {
                    "current_value": o.get("current_value"),
                    "priority": o.get("priority"),
                    "frequency": o.get("frequency"),
                    "status_override": o.get("status_override"),
                    "updated_at": o.get("updated_at"),
                },
                "$setOnInsert": {"department": o["department"], "role": o["role"], "metric": o["metric"]},
            },
            upsert=True,
        )

    # Scorecards (insert; preserve legacy id)
    # To keep it idempotent, we upsert by (legacy_id, created_at, created_by) which is stable for your data.
    for s in scorecards:
        try:
            kpis = json.loads(s.get("kpi_json") or "[]")
        except json.JSONDecodeError:
            kpis = []
        try:
            breakdown = json.loads(s.get("breakdown_json") or "[]")
        except json.JSONDecodeError:
            breakdown = []

        mongo_db["scorecards"].update_one(
            {"legacy_id": int(s["id"]), "created_at": s.get("created_at"), "created_by": s.get("created_by")},
            {
                "$set": {
                    "created_at": s.get("created_at"),
                    "review_date": s.get("review_date"),
                    "employee_name": s.get("employee_name"),
                    "department": s.get("department"),
                    "role": s.get("role"),
                    "final_score": float(s.get("final_score") or 0.0),
                    "rating": s.get("rating"),
                    "created_by": s.get("created_by"),
                    "review_cycle": s.get("review_cycle"),
                    "status": s.get("status"),
                    "self_comment": s.get("self_comment") or "",
                    "manager_comment": s.get("manager_comment") or "",
                    "evidence_url": s.get("evidence_url") or "",
                    "kpis": kpis,
                    "breakdown": breakdown,
                    "legacy_id": int(s["id"]),
                }
            },
            upsert=True,
        )

    # Audit logs (insert; best-effort idempotency by unique tuple)
    for a in audit_logs:
        mongo_db["audit_logs"].update_one(
            {
                "created_at": a.get("created_at"),
                "actor": a.get("actor"),
                "action": a.get("action"),
                "entity_type": a.get("entity_type"),
                "entity_id": a.get("entity_id"),
            },
            {"$setOnInsert": dict(a)},
            upsert=True,
        )

    print("Migration complete.")


if __name__ == "__main__":
    main()

