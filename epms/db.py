from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from epms.auth import generate_salt, hash_password
from epms.schema_meta import table_columns
from epms.sql_engine import get_engine


def env_bool(name: str, default: bool = False) -> bool:
    import os

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "y", "on"}


def init_db(
    db_path: Path,
    review_cycles: list[str],
    default_admin_username: str,
    default_admin_password: str,
    log_audit_callback,
) -> None:
    del db_path
    engine = get_engine()
    dialect = engine.dialect.name
    with engine.begin() as conn:
        _create_tables(conn, dialect)
        _ensure_user_extra_columns(conn, dialect)
        _ensure_scorecard_extra_columns(conn, dialect)
        seed_review_cycles(conn, dialect, review_cycles)
        if env_bool("EPMS_ENABLE_ADMIN_SEED", True):
            seed_default_admin(conn, dialect, default_admin_username, default_admin_password, log_audit_callback)


def _create_tables(conn, dialect: str) -> None:
    if dialect == "postgresql":
        id_pk = "SERIAL PRIMARY KEY"
        user_active = "SMALLINT NOT NULL DEFAULT 1"
    else:
        id_pk = "INTEGER PRIMARY KEY AUTOINCREMENT"
        user_active = "INTEGER NOT NULL DEFAULT 1"

    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS scorecards (
                id {id_pk},
                created_at TEXT NOT NULL,
                review_date TEXT NOT NULL,
                employee_name TEXT NOT NULL,
                department TEXT NOT NULL,
                role TEXT NOT NULL,
                final_score REAL NOT NULL,
                rating TEXT NOT NULL,
                kpi_json TEXT NOT NULL,
                breakdown_json TEXT NOT NULL,
                created_by TEXT NOT NULL,
                review_cycle TEXT,
                status TEXT,
                self_comment TEXT,
                manager_comment TEXT,
                evidence_url TEXT
            )
            """
        )
    )
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS users (
                id {id_pk},
                username TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                manager_username TEXT,
                department TEXT,
                is_active {user_active},
                created_at TEXT NOT NULL
            )
            """
        )
    )

    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id {id_pk},
                created_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT,
                details TEXT
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS review_cycles (
                cycle_name TEXT PRIMARY KEY,
                is_closed INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS kpi_registry_overrides (
                department TEXT NOT NULL,
                role TEXT NOT NULL,
                metric TEXT NOT NULL,
                current_value TEXT,
                priority TEXT DEFAULT 'P2',
                frequency TEXT DEFAULT 'Monthly',
                status_override TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (department, role, metric)
            )
            """
        )
    )


def _ensure_user_extra_columns(conn, dialect: str) -> None:
    cols = table_columns(conn, dialect, "users")
    if "manager_username" not in cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN manager_username TEXT"))
    if "department" not in cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN department TEXT"))


def _ensure_scorecard_extra_columns(conn, dialect: str) -> None:
    cols = table_columns(conn, dialect, "scorecards")
    desired = {
        "review_cycle": "TEXT",
        "status": "TEXT",
        "self_comment": "TEXT",
        "manager_comment": "TEXT",
        "evidence_url": "TEXT",
    }
    for column_name, column_type in desired.items():
        if column_name not in cols:
            conn.execute(text(f"ALTER TABLE scorecards ADD COLUMN {column_name} {column_type}"))


def seed_review_cycles(conn, dialect: str, review_cycles: list[str]) -> None:
    del dialect
    for cycle_name in review_cycles:
        existing = conn.execute(
            text("SELECT cycle_name FROM review_cycles WHERE cycle_name = :c"),
            {"c": cycle_name},
        ).fetchone()
        if not existing:
            conn.execute(
                text(
                    """
                    INSERT INTO review_cycles (cycle_name, is_closed, updated_at)
                    VALUES (:c, 0, :ts)
                    """
                ),
                {"c": cycle_name, "ts": datetime.now().isoformat()},
            )


def seed_default_admin(
    conn,
    dialect: str,
    username: str,
    password: str,
    log_audit_callback,
) -> None:
    del dialect
    existing_admin = conn.execute(
        text("SELECT id FROM users WHERE username = :u"),
        {"u": username},
    ).fetchone()
    if existing_admin:
        return

    salt = generate_salt()
    password_hash = hash_password(password, salt)
    conn.execute(
        text(
            """
            INSERT INTO users (username, role, password_hash, password_salt, is_active, created_at)
            VALUES (:u, 'Admin', :ph, :ps, 1, :ts)
            """
        ),
        {"u": username, "ph": password_hash, "ps": salt, "ts": datetime.now().isoformat()},
    )
    log_audit_callback("SEED_ADMIN", "user", username, "Default admin created.")
