from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from epms.auth import generate_salt, hash_password


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
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scorecards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                manager_username TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT,
                details TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_cycles (
                cycle_name TEXT PRIMARY KEY,
                is_closed INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        _ensure_columns(conn)
        _ensure_scorecard_columns(conn)
        seed_review_cycles(conn, review_cycles)
        if env_bool("EPMS_ENABLE_ADMIN_SEED", True):
            seed_default_admin(conn, default_admin_username, default_admin_password, log_audit_callback)


def _ensure_columns(conn: sqlite3.Connection) -> None:
    user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "manager_username" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN manager_username TEXT")


def _ensure_scorecard_columns(conn: sqlite3.Connection) -> None:
    scorecard_columns = {row[1] for row in conn.execute("PRAGMA table_info(scorecards)").fetchall()}
    desired_columns: dict[str, str] = {
        "review_cycle": "TEXT",
        "status": "TEXT",
        "self_comment": "TEXT",
        "manager_comment": "TEXT",
        "evidence_url": "TEXT",
    }
    for column_name, column_type in desired_columns.items():
        if column_name not in scorecard_columns:
            conn.execute(f"ALTER TABLE scorecards ADD COLUMN {column_name} {column_type}")


def seed_review_cycles(conn: sqlite3.Connection, review_cycles: list[str]) -> None:
    for cycle_name in review_cycles:
        existing = conn.execute(
            "SELECT cycle_name FROM review_cycles WHERE cycle_name = ?",
            (cycle_name,),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO review_cycles (cycle_name, is_closed, updated_at) VALUES (?, 0, ?)",
                (cycle_name, datetime.now().isoformat()),
            )


def seed_default_admin(
    conn: sqlite3.Connection,
    username: str,
    password: str,
    log_audit_callback,
) -> None:
    existing_admin = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing_admin:
        return
    salt = generate_salt()
    password_hash = hash_password(password, salt)
    conn.execute(
        """
        INSERT INTO users (username, role, password_hash, password_salt, is_active, created_at)
        VALUES (?, ?, ?, ?, 1, ?)
        """,
        (username, "Admin", password_hash, salt, datetime.now().isoformat()),
    )
    log_audit_callback("SEED_ADMIN", "user", username, "Default admin created.")
