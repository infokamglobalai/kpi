from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
import plotly.express as px
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from dotenv import load_dotenv

from epms import auth as auth_module
from epms import db_adapter as db_adapter_module
from epms import db as db_module
from epms import reports as reports_module
from epms import ui as ui_module

load_dotenv()


st.set_page_config(
    page_title="KamglobalAI EPMS",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = Path(os.getenv("EPMS_DB_PATH", "epms.db"))
DB_CONFIG = db_adapter_module.build_database_config(DB_PATH)
DEFAULT_ADMIN_USERNAME = os.getenv("EPMS_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("EPMS_ADMIN_PASSWORD", "Admin@123")
WORKFLOW_STATUSES = ["Draft", "Submitted", "Manager Reviewed", "Calibrated", "Finalized"]
REVIEW_CYCLES = ["Q1", "Q2", "Q3", "Q4", "Annual"]
FORCED_DISTRIBUTION_GUIDE = {
    "Outstanding": 10,
    "Exceeds Expectations": 20,
    "Meets Expectations": 55,
    "Needs Improvement": 15,
}


def env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "y", "on"}


CATEGORY_WEIGHTS: Dict[str, int] = {
    "Operational Excellence": 30,
    "Delivery & Timelines": 25,
    "Quality & Compliance": 20,
    "Documentation & Process": 10,
    "Innovation / Improvement": 10,
    "Collaboration & Communication": 5,
}


DEPARTMENTS: Dict[str, Dict[str, Dict[str, List[Dict[str, str | int]]]]] = {
    "IT Department": {
        "roles": {
            "IT Services Head": [
                {
                    "metric": "Server Uptime",
                    "target": ">= 99.9%",
                    "category": "Operational Excellence",
                    "weight": 30,
                },
                {
                    "metric": "Critical Downtime Resolution",
                    "target": "<= 1 hour",
                    "category": "Delivery & Timelines",
                    "weight": 25,
                },
                {
                    "metric": "Security Breach",
                    "target": "Zero",
                    "category": "Quality & Compliance",
                    "weight": 20,
                },
                {
                    "metric": "Cloud Cost Optimization",
                    "target": "10% saving",
                    "category": "Innovation / Improvement",
                    "weight": 10,
                },
                {
                    "metric": "Infrastructure Documentation",
                    "target": "100% updated",
                    "category": "Documentation & Process",
                    "weight": 10,
                },
            ],
            "Core Developer": [
                {
                    "metric": "API Response Time",
                    "target": "< 300ms",
                    "category": "Operational Excellence",
                    "weight": 30,
                },
                {
                    "metric": "Bug Resolution P1",
                    "target": "<= 4 hrs",
                    "category": "Delivery & Timelines",
                    "weight": 25,
                },
                {
                    "metric": "Deployment Failure",
                    "target": "Zero",
                    "category": "Quality & Compliance",
                    "weight": 20,
                },
                {
                    "metric": "New Feature Build",
                    "target": "2/month",
                    "category": "Innovation / Improvement",
                    "weight": 10,
                },
            ],
            "Tech Support": [
                {
                    "metric": "P1 Resolution Compliance",
                    "target": "100%",
                    "category": "Delivery & Timelines",
                    "weight": 25,
                },
                {
                    "metric": "First Response Time",
                    "target": "< 30 mins",
                    "category": "Operational Excellence",
                    "weight": 30,
                },
                {
                    "metric": "Customer Satisfaction",
                    "target": ">= 4.5/5",
                    "category": "Collaboration & Communication",
                    "weight": 5,
                },
                {
                    "metric": "Daily Reporting",
                    "target": "Daily",
                    "category": "Documentation & Process",
                    "weight": 10,
                },
            ],
        }
    },
    "Academics": {
        "roles": {
            "Academic Head": [
                {
                    "metric": "Curriculum Completion Rate",
                    "target": "100%",
                    "category": "Operational Excellence",
                    "weight": 30,
                },
                {
                    "metric": "Student Success Rate",
                    "target": "> 85%",
                    "category": "Quality & Compliance",
                    "weight": 20,
                },
                {
                    "metric": "Faculty Performance Score",
                    "target": "Avg > 4.0",
                    "category": "Collaboration & Communication",
                    "weight": 5,
                },
            ],
            "Subject Matter Expert (SME)": [
                {
                    "metric": "Content Production",
                    "target": "5 modules/week",
                    "category": "Delivery & Timelines",
                    "weight": 25,
                },
                {
                    "metric": "Technical Accuracy",
                    "target": "Zero Errors",
                    "category": "Quality & Compliance",
                    "weight": 20,
                },
                {
                    "metric": "Lesson Plan Documentation",
                    "target": "Weekly",
                    "category": "Documentation & Process",
                    "weight": 10,
                },
            ],
            "Academic Counselor": [
                {
                    "metric": "Query Resolution TAT",
                    "target": "< 4 hours",
                    "category": "Operational Excellence",
                    "weight": 30,
                },
                {
                    "metric": "Student Satisfaction Score",
                    "target": "> 4.5/5",
                    "category": "Collaboration & Communication",
                    "weight": 5,
                },
            ],
        }
    },
    "Sales": {
        "roles": {
            "Sales Head": [
                {
                    "metric": "Revenue Achievement",
                    "target": "100%",
                    "category": "Delivery & Timelines",
                    "weight": 25,
                },
                {
                    "metric": "Team Conversion Rate",
                    "target": "> 15%",
                    "category": "Operational Excellence",
                    "weight": 30,
                },
                {
                    "metric": "Sales Strategy Optimization",
                    "target": "Quarterly",
                    "category": "Innovation / Improvement",
                    "weight": 10,
                },
            ],
            "Sales Executive": [
                {
                    "metric": "Daily Calls/Connects",
                    "target": "50+",
                    "category": "Operational Excellence",
                    "weight": 30,
                },
                {
                    "metric": "Follow-up TAT",
                    "target": "< 24 hrs",
                    "category": "Delivery & Timelines",
                    "weight": 25,
                },
                {
                    "metric": "CRM Data Accuracy",
                    "target": "100%",
                    "category": "Documentation & Process",
                    "weight": 10,
                },
            ],
        }
    },
    "Digital Marketing": {
        "roles": {
            "Marketing Manager": [
                {
                    "metric": "ROI on Ad Spend",
                    "target": "> 3x",
                    "category": "Operational Excellence",
                    "weight": 30,
                },
                {
                    "metric": "Cost Per Lead Reduction",
                    "target": "10%",
                    "category": "Innovation / Improvement",
                    "weight": 10,
                },
            ],
            "SEO Specialist": [
                {
                    "metric": "Keyword Ranking",
                    "target": "Top 3 for 50%",
                    "category": "Operational Excellence",
                    "weight": 30,
                },
                {
                    "metric": "Blog Publishing Frequency",
                    "target": "4 posts/week",
                    "category": "Delivery & Timelines",
                    "weight": 25,
                },
            ],
        }
    },
    "HR": {
        "roles": {
            "HR Manager": [
                {
                    "metric": "Attrition Rate",
                    "target": "< 5%",
                    "category": "Quality & Compliance",
                    "weight": 20,
                },
                {
                    "metric": "Employee Satisfaction Score",
                    "target": "> 4.0/5",
                    "category": "Collaboration & Communication",
                    "weight": 5,
                },
                {
                    "metric": "Compliance Audit Score",
                    "target": "100%",
                    "category": "Operational Excellence",
                    "weight": 30,
                },
            ],
            "HR Recruiter": [
                {
                    "metric": "Time to Hire",
                    "target": "< 15 days",
                    "category": "Delivery & Timelines",
                    "weight": 25,
                },
                {
                    "metric": "Offer Acceptance Rate",
                    "target": "> 90%",
                    "category": "Operational Excellence",
                    "weight": 30,
                },
            ],
        }
    },
    "Admin": {
        "roles": {
            "Admin Manager": [
                {
                    "metric": "Vendor SLA Compliance",
                    "target": "100%",
                    "category": "Operational Excellence",
                    "weight": 30,
                },
                {
                    "metric": "Procurement Cost Savings",
                    "target": "5%",
                    "category": "Innovation / Improvement",
                    "weight": 10,
                },
            ],
            "Front Office Exec": [
                {
                    "metric": "Logbook Accuracy",
                    "target": "100%",
                    "category": "Documentation & Process",
                    "weight": 10,
                },
                {
                    "metric": "Visitor Handling",
                    "target": "Zero Complaints",
                    "category": "Collaboration & Communication",
                    "weight": 5,
                },
            ],
        }
    },
    "AI Department": {
        "roles": {
            "AI Lead": [
                {
                    "metric": "Model Accuracy",
                    "target": "> 95%",
                    "category": "Quality & Compliance",
                    "weight": 20,
                },
                {
                    "metric": "AI Project Delivery",
                    "target": "On Schedule",
                    "category": "Delivery & Timelines",
                    "weight": 25,
                },
            ],
            "AI Engineer": [
                {
                    "metric": "Model Training Efficiency",
                    "target": "Within Benchmark",
                    "category": "Operational Excellence",
                    "weight": 30,
                },
                {
                    "metric": "Code/API Bug Rate",
                    "target": "< 2%",
                    "category": "Quality & Compliance",
                    "weight": 20,
                },
            ],
        }
    },
    "Finance": {
        "roles": {
            "Finance Manager": [
                {
                    "metric": "Reporting Accuracy",
                    "target": "Zero Errors",
                    "category": "Quality & Compliance",
                    "weight": 20,
                },
                {
                    "metric": "Budget Variance",
                    "target": "< 5%",
                    "category": "Operational Excellence",
                    "weight": 30,
                },
            ],
            "Accountant": [
                {
                    "metric": "Invoice Processing TAT",
                    "target": "Same Day",
                    "category": "Delivery & Timelines",
                    "weight": 25,
                },
                {
                    "metric": "Collection Efficiency",
                    "target": "> 90%",
                    "category": "Operational Excellence",
                    "weight": 30,
                },
            ],
        }
    },
}


def generate_salt() -> str:
    return auth_module.generate_salt()


def hash_password(raw_password: str, salt: str) -> str:
    return auth_module.hash_password(raw_password, salt)


def verify_password(raw_password: str, salt: str, expected_hash: str) -> bool:
    return auth_module.verify_password(raw_password, salt, expected_hash)


def apply_branding() -> None:
    ui_module.apply_branding()


def init_db() -> None:
    db_module.init_db(
        db_path=DB_PATH,
        review_cycles=REVIEW_CYCLES,
        default_admin_username=DEFAULT_ADMIN_USERNAME,
        default_admin_password=DEFAULT_ADMIN_PASSWORD,
        log_audit_callback=log_audit,
    )


def _ensure_scorecard_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(scorecards)").fetchall()
    }
    desired_columns = {
        "review_cycle": "TEXT",
        "status": "TEXT",
        "self_comment": "TEXT",
        "manager_comment": "TEXT",
        "evidence_url": "TEXT",
    }
    for column_name, column_type in desired_columns.items():
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE scorecards ADD COLUMN {column_name} {column_type}")
    user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "manager_username" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN manager_username TEXT")


def seed_review_cycles(conn: sqlite3.Connection) -> None:
    for cycle_name in REVIEW_CYCLES:
        existing = conn.execute(
            "SELECT cycle_name FROM review_cycles WHERE cycle_name = ?",
            (cycle_name,),
        ).fetchone()
        if not existing:
            conn.execute(
                """
                INSERT INTO review_cycles (cycle_name, is_closed, updated_at)
                VALUES (?, 0, ?)
                """,
                (cycle_name, datetime.now().isoformat()),
            )


def fetch_review_cycles() -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(
            """
            SELECT cycle_name, is_closed, updated_at
            FROM review_cycles
            ORDER BY cycle_name
            """,
            conn,
        )


def is_cycle_closed(cycle_name: str) -> bool:
    if not cycle_name:
        return False
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT is_closed FROM review_cycles WHERE cycle_name = ?",
            (cycle_name,),
        ).fetchone()
    return bool(row[0]) if row else False


def set_cycle_closed(cycle_name: str, is_closed: bool) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE review_cycles
            SET is_closed = ?, updated_at = ?
            WHERE cycle_name = ?
            """,
            (1 if is_closed else 0, datetime.now().isoformat(), cycle_name),
        )
    state = "CLOSED" if is_closed else "OPENED"
    log_audit("UPDATE_CYCLE_STATUS", "review_cycle", cycle_name, f"Cycle={cycle_name};State={state}")


def log_audit(action: str, entity_type: str, entity_id: str, details: str) -> None:
    actor = st.session_state.get("username", "system")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO audit_logs (created_at, actor, action, entity_type, entity_id, details)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (datetime.now().isoformat(), actor, action, entity_type, entity_id, details),
        )


def seed_default_admin(conn: sqlite3.Connection) -> None:
    existing_admin = conn.execute(
        "SELECT id FROM users WHERE username = ?",
        (DEFAULT_ADMIN_USERNAME,),
    ).fetchone()
    if existing_admin:
        return

    salt = generate_salt()
    password_hash = hash_password(DEFAULT_ADMIN_PASSWORD, salt)
    conn.execute(
        """
        INSERT INTO users (username, role, password_hash, password_salt, is_active, created_at)
        VALUES (?, ?, ?, ?, 1, ?)
        """,
        (
            DEFAULT_ADMIN_USERNAME,
            "Admin",
            password_hash,
            salt,
            datetime.now().isoformat(),
        ),
    )
    log_audit("SEED_ADMIN", "user", DEFAULT_ADMIN_USERNAME, "Default admin created.")


def save_scorecard(record: Dict[str, str | float]) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO scorecards (
                created_at, review_date, employee_name, department, role,
                final_score, rating, kpi_json, breakdown_json, created_by,
                review_cycle, status, self_comment, manager_comment, evidence_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(record["created_at"]),
                str(record["review_date"]),
                str(record["employee_name"]),
                str(record["department"]),
                str(record["role"]),
                float(record["final_score"]),
                str(record["rating"]),
                str(record["kpi_json"]),
                str(record["breakdown_json"]),
                str(record["created_by"]),
                str(record.get("review_cycle", "")),
                str(record.get("status", "Submitted")),
                str(record.get("self_comment", "")),
                str(record.get("manager_comment", "")),
                str(record.get("evidence_url", "")),
            ),
        )
    log_audit(
        "CREATE_SCORECARD",
        "scorecard",
        str(cursor.lastrowid),
        f"Employee={record['employee_name']}; Department={record['department']}; Role={record['role']}",
    )


def update_scorecard(
    scorecard_id: int,
    review_date: str,
    employee_name: str,
    department: str,
    role: str,
    final_score: float,
    rating: str,
    kpi_json: str,
    breakdown_json: str,
    review_cycle: str,
    status: str,
    self_comment: str,
    evidence_url: str,
) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE scorecards
            SET review_date = ?, employee_name = ?, department = ?, role = ?,
                final_score = ?, rating = ?, kpi_json = ?, breakdown_json = ?,
                review_cycle = ?, status = ?, self_comment = ?, evidence_url = ?
            WHERE id = ?
            """,
            (
                review_date,
                employee_name,
                department,
                role,
                final_score,
                rating,
                kpi_json,
                breakdown_json,
                review_cycle,
                status,
                self_comment,
                evidence_url,
                scorecard_id,
            ),
        )
    log_audit("UPDATE_SCORECARD", "scorecard", str(scorecard_id), f"Status={status}")


def fetch_scorecards(
    department: str | None = None,
    role: str | None = None,
    review_cycle: str | None = None,
    status: str | None = None,
) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        query = """
            SELECT
                id, created_at, review_date, employee_name, department, role,
                final_score, rating, created_by, review_cycle, status, self_comment, manager_comment, evidence_url
            FROM scorecards
            WHERE 1=1
        """
        params: list[str] = []
        if department:
            query += " AND department = ?"
            params.append(department)
        if role:
            query += " AND role = ?"
            params.append(role)
        if review_cycle:
            query += " AND review_cycle = ?"
            params.append(review_cycle)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY id DESC"
        return pd.read_sql_query(query, conn, params=params)


def fetch_scorecard_by_id(scorecard_id: int) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT
                id, review_date, employee_name, department, role,
                final_score, rating, kpi_json, breakdown_json, created_by,
                review_cycle, status, self_comment, manager_comment, evidence_url
            FROM scorecards
            WHERE id = ?
            """,
            (scorecard_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "review_date": row[1],
        "employee_name": row[2],
        "department": row[3],
        "role": row[4],
        "final_score": row[5],
        "rating": row[6],
        "kpi_json": row[7],
        "breakdown_json": row[8],
        "created_by": row[9],
        "review_cycle": row[10],
        "status": row[11],
        "self_comment": row[12] or "",
        "manager_comment": row[13] or "",
        "evidence_url": row[14] or "",
    }


def update_scorecard_workflow(scorecard_id: int, status: str, manager_comment: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE scorecards
            SET status = ?, manager_comment = ?
            WHERE id = ?
            """,
            (status, manager_comment, scorecard_id),
        )
    log_audit(
        "UPDATE_WORKFLOW",
        "scorecard",
        str(scorecard_id),
        f"Status={status}; Comment={manager_comment}",
    )


def fetch_audit_logs(limit: int = 300) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(
            """
            SELECT created_at, actor, action, entity_type, entity_id, details
            FROM audit_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=[limit],
        )


def get_user_by_username(username: str) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT username, role, password_hash, password_salt, is_active, manager_username
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
    if not row:
        return None
    return {
        "username": row[0],
        "role": row[1],
        "password_hash": row[2],
        "password_salt": row[3],
        "is_active": bool(row[4]),
        "manager_username": row[5] or "",
    }


def create_user(username: str, password: str, role: str, manager_username: str = "") -> tuple[bool, str]:
    username = username.strip().lower()
    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password) < 8:
        return False, "Password must be at least 8 characters."

    salt = generate_salt()
    password_hash = hash_password(password, salt)
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO users (username, role, password_hash, password_salt, manager_username, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (username, role, password_hash, salt, manager_username or None, datetime.now().isoformat()),
            )
    except sqlite3.IntegrityError:
        return False, "Username already exists."
    log_audit("CREATE_USER", "user", username, f"Role={role};Manager={manager_username or '-'}")
    return True, "User created successfully."


def fetch_users() -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        query = """
            SELECT id, username, role, manager_username, is_active, created_at
            FROM users
            ORDER BY username ASC
        """
        users_df = pd.read_sql_query(query, conn)
    users_df["is_active"] = users_df["is_active"].map({1: "Yes", 0: "No"})
    return users_df


def fetch_team_usernames(manager_username: str) -> list[str]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT username
            FROM users
            WHERE manager_username = ? AND is_active = 1
            """,
            (manager_username,),
        ).fetchall()
    return [row[0] for row in rows]


def get_visible_scorecards_for_current_user(**filters: str | None) -> pd.DataFrame:
    role = st.session_state.role
    username = st.session_state.username
    df = fetch_scorecards(
        department=filters.get("department"),
        role=filters.get("role"),
        review_cycle=filters.get("review_cycle"),
        status=filters.get("status"),
    )
    if df.empty:
        return df
    if role == "Admin":
        return df
    if role == "Manager":
        team = set(fetch_team_usernames(username))
        allowed = team | {username}
        return df[df["created_by"].isin(allowed)]
    if role == "Employee":
        return df[df["created_by"] == username]
    return df


def can_edit_scorecard(record: dict, role: str, username: str) -> tuple[bool, str]:
    cycle = str(record.get("review_cycle", "") or "")
    status = str(record.get("status", "") or "")
    created_by = str(record.get("created_by", "") or "")

    if is_cycle_closed(cycle):
        return False, f"Review cycle {cycle} is closed."
    if status in {"Calibrated", "Finalized"}:
        return False, f"Record is locked at status '{status}'."
    if role == "Admin":
        return True, ""
    if role == "Manager":
        allowed = set(fetch_team_usernames(username)) | {username}
        if created_by not in allowed:
            return False, "You can edit only your own/team records."
        if status not in {"Draft", "Submitted"}:
            return False, "Managers can edit only Draft/Submitted records."
        return True, ""
    if role == "Employee":
        if created_by != username:
            return False, "You can edit only your own records."
        if status not in {"Draft", "Submitted"}:
            return False, "You can edit only Draft/Submitted records."
        return True, ""
    return False, "Your role does not permit editing."


def set_user_status(username: str, is_active: bool) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE users SET is_active = ? WHERE username = ?",
            (1 if is_active else 0, username),
        )
    log_audit(
        "UPDATE_USER_STATUS",
        "user",
        username,
        f"IsActive={is_active}",
    )


def reset_user_password(username: str, new_password: str) -> tuple[bool, str]:
    if len(new_password) < 8:
        return False, "Password must be at least 8 characters."
    salt = generate_salt()
    password_hash = hash_password(new_password, salt)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE users
            SET password_hash = ?, password_salt = ?
            WHERE username = ?
            """,
            (password_hash, salt, username),
        )
    log_audit("RESET_PASSWORD", "user", username, "Password reset by admin.")
    return True, "Password reset successfully."


def initialize_session() -> None:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "username" not in st.session_state:
        st.session_state.username = ""
    if "role" not in st.session_state:
        st.session_state.role = ""


def get_rating(score: float) -> str:
    if score >= 4.5:
        return "Outstanding"
    if score >= 4.0:
        return "Exceeds Expectations"
    if score >= 3.0:
        return "Meets Expectations"
    return "Needs Improvement"


def calculate_weighted_score(kpi_scores: List[Dict[str, str | int | float]]) -> tuple[float, pd.DataFrame]:
    category_groups: Dict[str, List[float]] = {}
    for item in kpi_scores:
        category = str(item["category"])
        score = float(item["score"])
        category_groups.setdefault(category, []).append(score)

    detail_rows = []
    final_score = 0.0
    for category, weight in CATEGORY_WEIGHTS.items():
        scores = category_groups.get(category, [])
        category_average = sum(scores) / len(scores) if scores else 0.0
        weighted_value = (category_average * weight) / 100
        final_score += weighted_value
        detail_rows.append(
            {
                "Category": category,
                "Weight (%)": weight,
                "KPI Count": len(scores),
                "Category Avg Score": round(category_average, 2),
                "Weighted Contribution": round(weighted_value, 3),
            }
        )

    return round(final_score, 3), pd.DataFrame(detail_rows)


def build_report_pdf(report_df: pd.DataFrame) -> bytes:
    return reports_module.build_report_pdf(report_df)


def login_page() -> None:
    left, center, right = st.columns([1, 1.6, 1])
    with center:
        st.markdown('<div class="brand-title">KamglobalAI EPMS</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="brand-subtitle">Secure login for role-based performance management</div>',
            unsafe_allow_html=True,
        )
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username").strip().lower()
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            user = get_user_by_username(username)
            if not user:
                st.error("Invalid username or password.")
                return
            if not user["is_active"]:
                st.error("Your account is inactive. Contact administrator.")
                return
            if verify_password(password, str(user["password_salt"]), str(user["password_hash"])):
                st.session_state.authenticated = True
                st.session_state.username = username
                st.session_state.role = str(user["role"])
                st.success("Login successful.")
                st.rerun()
            else:
                st.error("Invalid username or password.")
        st.info("Initial admin login: admin / Admin@123")


def user_management_page() -> None:
    st.title("User Management")
    st.caption("Admin-only controls to create users, activate/deactivate accounts, and reset passwords.")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Create User")
        with st.form("create_user_form", clear_on_submit=True):
            new_username = st.text_input("Username", placeholder="e.g. manager1").strip().lower()
            new_password = st.text_input("Password", type="password")
            new_role = st.selectbox("Role", ["Manager", "Employee", "Viewer", "Admin"])
            managers_df = fetch_users()
            manager_options = [""] + managers_df[managers_df["role"] == "Manager"]["username"].tolist()
            manager_mapping = st.selectbox(
                "Reporting Manager (for Employee role)",
                manager_options,
                help="Select manager if the new user is an Employee.",
            )
            create_submit = st.form_submit_button("Create User", use_container_width=True)
        if create_submit:
            assigned_manager = manager_mapping if new_role == "Employee" else ""
            ok, message = create_user(new_username, new_password, new_role, assigned_manager)
            if ok:
                st.success(message)
            else:
                st.error(message)

    with c2:
        st.subheader("Account Actions")
        users_df = fetch_users()
        available_users = users_df["username"].tolist()
        if available_users:
            action_user = st.selectbox("Select User", available_users)
            selected_status = users_df.loc[users_df["username"] == action_user, "is_active"].iloc[0] == "Yes"
            toggle_label = "Deactivate User" if selected_status else "Activate User"
            if st.button(toggle_label, use_container_width=True):
                if action_user == DEFAULT_ADMIN_USERNAME and selected_status:
                    st.error("Default admin cannot be deactivated.")
                else:
                    set_user_status(action_user, not selected_status)
                    st.success("User status updated.")
                    st.rerun()

            with st.form("reset_password_form", clear_on_submit=True):
                reset_password = st.text_input("New Password", type="password")
                reset_submit = st.form_submit_button("Reset Password", use_container_width=True)
            if reset_submit:
                ok, message = reset_user_password(action_user, reset_password)
                if ok:
                    st.success(message)
                else:
                    st.error(message)

    st.subheader("Users")
    st.dataframe(fetch_users(), use_container_width=True, hide_index=True)
    st.subheader("Recent Audit Logs")
    st.dataframe(fetch_audit_logs(150), use_container_width=True, hide_index=True)


def dashboard_page() -> None:
    st.markdown('<div class="brand-title">KamglobalAI Enterprise Performance Management System</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="brand-subtitle">Centralized KPI tracking and weighted performance management dashboard</div>',
        unsafe_allow_html=True,
    )

    all_roles = sum(len(dept_data["roles"]) for dept_data in DEPARTMENTS.values())
    all_kpis = sum(
        len(role_kpis)
        for dept_data in DEPARTMENTS.values()
        for role_kpis in dept_data["roles"].values()
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Departments", len(DEPARTMENTS))
    c2.metric("Roles", all_roles)
    c3.metric("Total KPI Definitions", all_kpis)

    scorecards_df = get_visible_scorecards_for_current_user()
    d1, d2, d3 = st.columns(3)
    d1.metric("Total Reviews", len(scorecards_df))
    avg_value = scorecards_df["final_score"].mean() if not scorecards_df.empty else 0.0
    d2.metric("Average Score", f"{avg_value:.2f}")
    submitted_count = int((scorecards_df.get("status", pd.Series(dtype=str)) == "Submitted").sum())
    d3.metric("Pending Manager Review", submitted_count)
    p1, p2, p3 = st.columns(3)
    role = st.session_state.role
    username = st.session_state.username
    if role == "Employee":
        p1.metric("My Drafts", int((scorecards_df.get("status", pd.Series(dtype=str)) == "Draft").sum()))
        p2.metric("My Submitted", submitted_count)
        p3.metric("My Finalized", int((scorecards_df.get("status", pd.Series(dtype=str)) == "Finalized").sum()))
    elif role == "Manager":
        team = set(fetch_team_usernames(username))
        team_df = scorecards_df[scorecards_df["created_by"].isin(team)] if not scorecards_df.empty else scorecards_df
        p1.metric("Team Pending Review", int((team_df.get("status", pd.Series(dtype=str)) == "Submitted").sum()))
        p2.metric("Team Calibrated", int((team_df.get("status", pd.Series(dtype=str)) == "Calibrated").sum()))
        p3.metric("Team Finalized", int((team_df.get("status", pd.Series(dtype=str)) == "Finalized").sum()))
    else:
        p1.metric("Total Drafts", int((scorecards_df.get("status", pd.Series(dtype=str)) == "Draft").sum()))
        p2.metric("Calibrated", int((scorecards_df.get("status", pd.Series(dtype=str)) == "Calibrated").sum()))
        p3.metric("Finalized", int((scorecards_df.get("status", pd.Series(dtype=str)) == "Finalized").sum()))

    weight_df = pd.DataFrame(
        {"Category": list(CATEGORY_WEIGHTS.keys()), "Weight": list(CATEGORY_WEIGHTS.values())}
    )
    fig = px.pie(
        weight_df,
        values="Weight",
        names="Category",
        hole=0.35,
        title="Universal Evaluation Logic - Category Weightage",
        color_discrete_sequence=px.colors.sequential.Blues_r,
    )
    st.plotly_chart(fig, use_container_width=True)

    dept_rows = []
    for dept_name, dept_data in DEPARTMENTS.items():
        for role_name, role_kpis in dept_data["roles"].items():
            dept_rows.append(
                {
                    "Department": dept_name,
                    "Role": role_name,
                    "No. of KPIs": len(role_kpis),
                }
            )
    st.subheader("Organization KPI Map")
    st.dataframe(pd.DataFrame(dept_rows), use_container_width=True, hide_index=True)


def scorecard_page() -> None:
    st.title("KPI Scorecard Entry")
    st.caption("Select department, role, and score each KPI on a 1-5 scale.")

    role = st.session_state.role
    username = st.session_state.username
    editable_df = get_visible_scorecards_for_current_user(status=None)
    if not editable_df.empty:
        editable_df = editable_df[
            editable_df.apply(
                lambda row: can_edit_scorecard(row.to_dict(), role, username)[0],
                axis=1,
            )
        ]

    entry_mode = st.radio("Entry Mode", ["New Record", "Edit Existing"], horizontal=True)
    edit_record = None
    if entry_mode == "Edit Existing":
        if editable_df.empty:
            st.warning("No editable records available.")
            return
        selectable = editable_df[["id", "employee_name", "department", "role", "status", "review_cycle"]]
        st.dataframe(selectable, use_container_width=True, hide_index=True)
        selected_id = st.selectbox("Select Record ID", selectable["id"].tolist())
        edit_record = fetch_scorecard_by_id(int(selected_id))
        if not edit_record:
            st.error("Selected record not found.")
            return
        if role == "Employee" and edit_record["created_by"] != username:
            st.error("You can only edit your own records.")
            return

    departments = list(DEPARTMENTS.keys())
    c1, c2 = st.columns(2)
    default_department = edit_record["department"] if edit_record else departments[0]
    department = c1.selectbox("Department", departments, index=departments.index(default_department))
    roles = list(DEPARTMENTS[department]["roles"].keys())
    default_role = edit_record["role"] if edit_record and edit_record["role"] in roles else roles[0]
    selected_role = c2.selectbox("Role", roles, index=roles.index(default_role))

    c3, c4 = st.columns(2)
    employee_default = edit_record["employee_name"] if edit_record else ""
    if role == "Employee":
        employee_name = c3.text_input("Employee Name", value=username, disabled=True)
    else:
        employee_name = c3.text_input(
            "Employee Name",
            value=employee_default,
            placeholder="Enter employee full name",
        )
    default_review_date = (
        datetime.strptime(edit_record["review_date"], "%Y-%m-%d").date()
        if edit_record and edit_record["review_date"]
        else date.today()
    )
    review_date = c4.date_input("Review Date", value=default_review_date)
    c5, c6 = st.columns(2)
    default_cycle = edit_record["review_cycle"] if edit_record and edit_record["review_cycle"] in REVIEW_CYCLES else REVIEW_CYCLES[0]
    review_cycle = c5.selectbox("Review Cycle", REVIEW_CYCLES, index=REVIEW_CYCLES.index(default_cycle))
    if is_cycle_closed(review_cycle):
        st.warning(f"{review_cycle} is currently closed. Records in this cycle cannot be created or edited.")
    evidence_url = c6.text_input(
        "Evidence URL (optional)",
        value=edit_record["evidence_url"] if edit_record else "",
        placeholder="https://...",
    )
    self_comment = st.text_area(
        "Self Comment / Notes",
        value=edit_record["self_comment"] if edit_record else "",
        placeholder="Optional qualitative assessment",
    )
    status_choice = st.selectbox(
        "Record Status",
        ["Draft", "Submitted"] if role == "Employee" else ["Draft", "Submitted", "Manager Reviewed"],
        index=(
            0
            if not edit_record
            else (
                ["Draft", "Submitted"] if role == "Employee" else ["Draft", "Submitted", "Manager Reviewed"]
            ).index(edit_record["status"])
            if edit_record["status"] in (["Draft", "Submitted"] if role == "Employee" else ["Draft", "Submitted", "Manager Reviewed"])
            else 0
        ),
    )

    role_kpis = DEPARTMENTS[department]["roles"][selected_role]
    existing_scores = {}
    if edit_record and edit_record["kpi_json"]:
        for item in json.loads(edit_record["kpi_json"]):
            existing_scores[str(item.get("metric"))] = int(item.get("score", 3))

    with st.form("scorecard_form", clear_on_submit=False):
        st.markdown("### KPI Ratings")
        kpi_scores: List[Dict[str, str | int | float]] = []
        for idx, kpi in enumerate(role_kpis):
            slider_label = f"{kpi['metric']}  |  Target: {kpi['target']}  |  Category: {kpi['category']}"
            score_value = st.slider(
                label=slider_label,
                min_value=1,
                max_value=5,
                value=existing_scores.get(str(kpi["metric"]), 3),
                key=f"{department}_{selected_role}_{idx}",
            )
            kpi_scores.append(
                {
                    "metric": kpi["metric"],
                    "target": kpi["target"],
                    "category": kpi["category"],
                    "weight": kpi["weight"],
                    "score": score_value,
                }
            )

        submitted = st.form_submit_button("Save Scorecard", use_container_width=True)

    if submitted:
        if not employee_name.strip():
            st.error("Employee Name is required.")
            return
        if is_cycle_closed(review_cycle):
            st.error(f"{review_cycle} is closed. Please choose an open cycle.")
            return

        final_score, breakdown_df = calculate_weighted_score(kpi_scores)
        rating = get_rating(final_score)

        m1, m2 = st.columns(2)
        m1.metric("Final Weighted Score", f"{final_score:.2f} / 5.00")
        m2.metric("Performance Rating", rating)

        st.markdown("### Category-wise Breakdown")
        st.dataframe(breakdown_df, use_container_width=True, hide_index=True)

        st.markdown("### KPI Scorecard Details")
        scorecard_df = pd.DataFrame(kpi_scores)
        st.dataframe(scorecard_df, use_container_width=True, hide_index=True)

        record = {
            "created_at": datetime.now().isoformat(),
            "review_date": str(review_date),
            "employee_name": employee_name.strip(),
            "department": department,
            "role": selected_role,
            "final_score": round(final_score, 3),
            "rating": rating,
            "kpi_json": json.dumps(kpi_scores),
            "breakdown_json": breakdown_df.to_json(orient="records"),
            "created_by": st.session_state.username,
            "review_cycle": review_cycle,
            "status": status_choice,
            "self_comment": self_comment.strip(),
            "manager_comment": "",
            "evidence_url": evidence_url.strip(),
        }
        if edit_record:
            allowed, reason = can_edit_scorecard(edit_record, role, username)
            if not allowed:
                st.error(reason)
                return
            update_scorecard(
                scorecard_id=int(edit_record["id"]),
                review_date=str(review_date),
                employee_name=employee_name.strip(),
                department=department,
                role=selected_role,
                final_score=round(final_score, 3),
                rating=rating,
                kpi_json=json.dumps(kpi_scores),
                breakdown_json=breakdown_df.to_json(orient="records"),
                review_cycle=review_cycle,
                status=status_choice,
                self_comment=self_comment.strip(),
                evidence_url=evidence_url.strip(),
            )
            st.success("Scorecard updated successfully.")
        else:
            save_scorecard(record)
            st.success("Scorecard saved successfully. Data is persisted in SQLite and visible in Reports.")


def review_workflow_page() -> None:
    st.title("Review Workflow")
    st.caption("Manager/Admin workflow for review progression and manager feedback.")

    pending_df = get_visible_scorecards_for_current_user(status="Submitted")
    if pending_df.empty:
        st.info("No submitted scorecards are pending review.")
        return

    st.dataframe(
        pending_df[
            ["id", "review_date", "employee_name", "department", "role", "review_cycle", "final_score", "rating", "created_by"]
        ],
        use_container_width=True,
        hide_index=True,
    )

    selected_id = st.selectbox("Select Scorecard ID", pending_df["id"].tolist())
    selected_record = pending_df[pending_df["id"] == selected_id].iloc[0]

    c1, c2 = st.columns(2)
    next_status = c1.selectbox("Update Status", WORKFLOW_STATUSES[2:], index=0)
    manager_comment = c2.text_input("Manager Comment", placeholder="Review notes")
    if st.button("Apply Workflow Update", use_container_width=True):
        if is_cycle_closed(str(selected_record["review_cycle"] or "")):
            st.error(f"{selected_record['review_cycle']} is closed. Workflow updates are locked.")
            return
        update_scorecard_workflow(int(selected_id), next_status, manager_comment.strip())
        st.success(f"Scorecard {selected_id} moved to {next_status}.")
        st.rerun()

    with st.expander("Selected Scorecard Details", expanded=False):
        st.write(f"Employee: {selected_record['employee_name']}")
        st.write(f"Cycle: {selected_record['review_cycle']}")
        st.write(f"Self Comment: {selected_record['self_comment'] or '-'}")
        if selected_record["evidence_url"]:
            st.markdown(f"[Evidence Link]({selected_record['evidence_url']})")


def reports_page() -> None:
    st.title("Performance Reports")
    st.caption("Review saved scorecards and export as CSV / PDF.")

    f1, f2, f3, f4 = st.columns(4)
    dept_filter = f1.selectbox("Department", ["All"] + list(DEPARTMENTS.keys()))
    all_roles = sorted({role for dept in DEPARTMENTS.values() for role in dept["roles"].keys()})
    role_filter = f2.selectbox("Role", ["All"] + all_roles)
    cycle_filter = f3.selectbox("Review Cycle", ["All"] + REVIEW_CYCLES)
    status_filter = f4.selectbox("Status", ["All"] + WORKFLOW_STATUSES)

    report_df = get_visible_scorecards_for_current_user(
        department=None if dept_filter == "All" else dept_filter,
        role=None if role_filter == "All" else role_filter,
        review_cycle=None if cycle_filter == "All" else cycle_filter,
        status=None if status_filter == "All" else status_filter,
    )
    if report_df.empty:
        st.info("No scorecards submitted yet. Use 'Scorecard Entry' to add performance records.")
        return

    st.dataframe(report_df, use_container_width=True, hide_index=True)

    avg_score = report_df["final_score"].mean()
    outstanding_count = (report_df["rating"] == "Outstanding").sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Average Final Score", f"{avg_score:.2f}")
    c2.metric("Outstanding Count", int(outstanding_count))
    c3.metric("Total Reviews", len(report_df))

    trend_df = report_df.copy()
    trend_df["review_date"] = pd.to_datetime(trend_df["review_date"], errors="coerce")
    trend_df = trend_df.dropna(subset=["review_date"]).sort_values("review_date")
    if not trend_df.empty:
        trend_chart = px.line(
            trend_df,
            x="review_date",
            y="final_score",
            color="department",
            markers=True,
            title="Score Trend by Review Date",
        )
        st.plotly_chart(trend_chart, use_container_width=True)

    csv_data = report_df.to_csv(index=False).encode("utf-8")
    pdf_data = build_report_pdf(report_df)

    d1, d2 = st.columns(2)
    d1.download_button(
        label="Download CSV",
        data=csv_data,
        file_name="kamglobalai_epms_report.csv",
        mime="text/csv",
        use_container_width=True,
    )
    d2.download_button(
        label="Download PDF",
        data=pdf_data,
        file_name="kamglobalai_epms_report.pdf",
        mime="application/pdf",
        use_container_width=True,
    )


def calibration_page() -> None:
    st.title("Calibration Panel")
    st.caption("Distribution analysis versus recommended forced-distribution guidance.")

    c1, c2 = st.columns(2)
    cycle_filter = c1.selectbox("Review Cycle", ["All"] + REVIEW_CYCLES)
    dept_filter = c2.selectbox("Department", ["All"] + list(DEPARTMENTS.keys()))

    df = get_visible_scorecards_for_current_user(
        review_cycle=None if cycle_filter == "All" else cycle_filter,
        department=None if dept_filter == "All" else dept_filter,
    )
    if df.empty:
        st.info("No records available for calibration.")
        return

    dist_df = df["rating"].value_counts().rename_axis("rating").reset_index(name="count")
    total = int(dist_df["count"].sum())
    dist_df["actual_pct"] = (dist_df["count"] / total * 100).round(1)
    dist_df["recommended_pct"] = dist_df["rating"].map(FORCED_DISTRIBUTION_GUIDE).fillna(0)
    dist_df["variance_pct"] = (dist_df["actual_pct"] - dist_df["recommended_pct"]).round(1)

    st.dataframe(dist_df, use_container_width=True, hide_index=True)
    fig = px.bar(
        dist_df.melt(id_vars="rating", value_vars=["actual_pct", "recommended_pct"]),
        x="rating",
        y="value",
        color="variable",
        barmode="group",
        title="Actual vs Recommended Distribution (%)",
    )
    st.plotly_chart(fig, use_container_width=True)


def cycle_controls_page() -> None:
    st.title("Cycle Controls")
    st.caption("Admin controls to open/close review cycles and freeze modifications.")
    cycles_df = fetch_review_cycles()
    if cycles_df.empty:
        st.info("No review cycles available.")
        return

    display_df = cycles_df.copy()
    display_df["is_closed"] = display_df["is_closed"].map({1: "Closed", 0: "Open"})
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    cycle_name = st.selectbox("Select Cycle", cycles_df["cycle_name"].tolist())
    is_closed = bool(cycles_df.loc[cycles_df["cycle_name"] == cycle_name, "is_closed"].iloc[0])
    toggle_label = "Open Cycle" if is_closed else "Close Cycle"
    if st.button(toggle_label, use_container_width=True):
        set_cycle_closed(cycle_name, not is_closed)
        state = "closed" if not is_closed else "opened"
        st.success(f"{cycle_name} has been {state}.")
        st.rerun()


def main() -> None:
    apply_branding()
    initialize_session()
    init_db()

    if not st.session_state.authenticated:
        login_page()
        return

    st.sidebar.title("KamglobalAI EPMS")
    st.sidebar.caption(f"User: {st.session_state.username} ({st.session_state.role})")
    st.sidebar.caption(f"DB Backend: {DB_CONFIG.backend}")

    allowed_pages_by_role = {
        "Admin": ["Dashboard", "Scorecard Entry", "Review Workflow", "Calibration", "Cycle Controls", "Reports", "User Management"],
        "Manager": ["Dashboard", "Scorecard Entry", "Review Workflow", "Calibration", "Reports"],
        "Employee": ["Dashboard", "Scorecard Entry", "Reports"],
        "Viewer": ["Dashboard", "Reports"],
    }
    pages = allowed_pages_by_role.get(st.session_state.role, ["Dashboard"])
    page = st.sidebar.radio("Go to", pages)

    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.username = ""
        st.session_state.role = ""
        st.rerun()

    if page == "Dashboard":
        dashboard_page()
    elif page == "Scorecard Entry":
        scorecard_page()
    elif page == "Review Workflow":
        review_workflow_page()
    elif page == "Calibration":
        calibration_page()
    elif page == "Cycle Controls":
        cycle_controls_page()
    elif page == "User Management":
        user_management_page()
    else:
        reports_page()


if __name__ == "__main__":
    main()
