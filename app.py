from __future__ import annotations

import hashlib
import io
import json
import os
import re
import secrets
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
from epms import db as db_module
from epms import reports as reports_module
from epms import ui as ui_module
from epms.emailer import send_email_smtp
from epms.mongo import get_db
from pymongo.errors import DuplicateKeyError
from bson import ObjectId

load_dotenv()


st.set_page_config(
    page_title="KamglobalAI EPMS",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = Path(os.getenv("EPMS_DB_PATH", "epms.db"))
DB_BACKEND = "mongodb"
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


def _oid(value: str | ObjectId) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    return ObjectId(str(value))


def fetch_review_cycles() -> pd.DataFrame:
    db = get_db()
    rows = list(db["review_cycles"].find({}, {"_id": 0}))
    if not rows:
        return pd.DataFrame(columns=["cycle_name", "is_closed", "updated_at"])
    df = pd.DataFrame(rows)
    if "cycle_name" in df.columns:
        df = df.sort_values("cycle_name")
    return df


def is_cycle_closed(cycle_name: str) -> bool:
    if not cycle_name:
        return False
    db = get_db()
    doc = db["review_cycles"].find_one({"cycle_name": cycle_name}, {"is_closed": 1})
    if not doc:
        return False
    return bool(doc.get("is_closed"))


def set_cycle_closed(cycle_name: str, is_closed: bool) -> None:
    db = get_db()
    db["review_cycles"].update_one(
        {"cycle_name": cycle_name},
        {"$set": {"is_closed": 1 if is_closed else 0, "updated_at": datetime.now().isoformat()}},
        upsert=True,
    )
    state = "CLOSED" if is_closed else "OPENED"
    log_audit("UPDATE_CYCLE_STATUS", "review_cycle", cycle_name, f"Cycle={cycle_name};State={state}")


def log_audit(action: str, entity_type: str, entity_id: str, details: str) -> None:
    actor = st.session_state.get("username", "system")
    db = get_db()
    db["audit_logs"].insert_one(
        {
            "created_at": datetime.now().isoformat(),
            "actor": actor,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "details": details,
        }
    )


def save_scorecard(record: Dict[str, str | float]) -> None:
    db = get_db()
    kpis = []
    breakdown = []
    try:
        kpis = json.loads(str(record.get("kpi_json", "[]") or "[]"))
    except json.JSONDecodeError:
        kpis = []
    try:
        breakdown = json.loads(str(record.get("breakdown_json", "[]") or "[]"))
    except json.JSONDecodeError:
        breakdown = []

    doc = {
        "created_at": str(record["created_at"]),
        "review_date": str(record["review_date"]),
        "employee_name": str(record["employee_name"]),
        "department": str(record["department"]),
        "role": str(record["role"]),
        "final_score": float(record["final_score"]),
        "rating": str(record["rating"]),
        "created_by": str(record["created_by"]),
        "review_cycle": str(record.get("review_cycle", "")),
        "status": str(record.get("status", "Submitted")),
        "self_comment": str(record.get("self_comment", "")),
        "manager_comment": str(record.get("manager_comment", "")),
        "evidence_url": str(record.get("evidence_url", "")),
        "kpis": kpis,
        "breakdown": breakdown,
    }
    new_id = db["scorecards"].insert_one(doc).inserted_id
    log_audit(
        "CREATE_SCORECARD",
        "scorecard",
        str(new_id),
        f"Employee={record['employee_name']}; Department={record['department']}; Role={record['role']}",
    )


def update_scorecard(
    scorecard_id: str,
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
    db = get_db()
    kpis = []
    breakdown = []
    try:
        kpis = json.loads(kpi_json or "[]")
    except json.JSONDecodeError:
        kpis = []
    try:
        breakdown = json.loads(breakdown_json or "[]")
    except json.JSONDecodeError:
        breakdown = []

    db["scorecards"].update_one(
        {"_id": _oid(scorecard_id)},
        {
            "$set": {
                "review_date": review_date,
                "employee_name": employee_name,
                "department": department,
                "role": role,
                "final_score": float(final_score),
                "rating": rating,
                "review_cycle": review_cycle,
                "status": status,
                "self_comment": self_comment,
                "evidence_url": evidence_url,
                "kpis": kpis,
                "breakdown": breakdown,
            }
        },
    )
    log_audit("UPDATE_SCORECARD", "scorecard", str(scorecard_id), f"Status={status}")


def fetch_scorecards(
    department: str | None = None,
    role: str | None = None,
    review_cycle: str | None = None,
    status: str | None = None,
) -> pd.DataFrame:
    db = get_db()
    q: dict = {}
    if department:
        q["department"] = department
    if role:
        q["role"] = role
    if review_cycle:
        q["review_cycle"] = review_cycle
    if status:
        q["status"] = status

    projection = {
        "_id": 1,
        "created_at": 1,
        "review_date": 1,
        "employee_name": 1,
        "department": 1,
        "role": 1,
        "final_score": 1,
        "rating": 1,
        "created_by": 1,
        "review_cycle": 1,
        "status": 1,
        "self_comment": 1,
        "manager_comment": 1,
        "evidence_url": 1,
    }
    docs = list(db["scorecards"].find(q, projection).sort("created_at", -1))
    if not docs:
        return pd.DataFrame(
            columns=[
                "id",
                "created_at",
                "review_date",
                "employee_name",
                "department",
                "role",
                "final_score",
                "rating",
                "created_by",
                "review_cycle",
                "status",
                "self_comment",
                "manager_comment",
                "evidence_url",
            ]
        )
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return pd.DataFrame(docs)


def fetch_scorecard_by_id(scorecard_id: str) -> dict | None:
    db = get_db()
    doc = db["scorecards"].find_one({"_id": _oid(scorecard_id)})
    if not doc:
        return None
    return {
        "id": str(doc.get("_id")),
        "review_date": doc.get("review_date", ""),
        "employee_name": doc.get("employee_name", ""),
        "department": doc.get("department", ""),
        "role": doc.get("role", ""),
        "final_score": float(doc.get("final_score") or 0.0),
        "rating": doc.get("rating", ""),
        "kpi_json": json.dumps(doc.get("kpis") or []),
        "breakdown_json": json.dumps(doc.get("breakdown") or []),
        "created_by": doc.get("created_by", ""),
        "review_cycle": doc.get("review_cycle", ""),
        "status": doc.get("status", ""),
        "self_comment": doc.get("self_comment") or "",
        "manager_comment": doc.get("manager_comment") or "",
        "evidence_url": doc.get("evidence_url") or "",
        "created_at": doc.get("created_at", ""),
    }


def update_scorecard_workflow(scorecard_id: str, status: str, manager_comment: str) -> None:
    db = get_db()
    db["scorecards"].update_one(
        {"_id": _oid(scorecard_id)},
        {"$set": {"status": status, "manager_comment": manager_comment}},
    )
    log_audit(
        "UPDATE_WORKFLOW",
        "scorecard",
        str(scorecard_id),
        f"Status={status}; Comment={manager_comment}",
    )


def fetch_audit_logs(limit: int = 300) -> pd.DataFrame:
    lim = max(1, min(int(limit), 5000))
    db = get_db()
    docs = list(
        db["audit_logs"]
        .find({}, {"_id": 0, "created_at": 1, "actor": 1, "action": 1, "entity_type": 1, "entity_id": 1, "details": 1})
        .sort("created_at", -1)
        .limit(lim)
    )
    if not docs:
        return pd.DataFrame(columns=["created_at", "actor", "action", "entity_type", "entity_id", "details"])
    return pd.DataFrame(docs)


def get_user_by_username(username: str) -> dict | None:
    db = get_db()
    doc = db["users"].find_one({"username": username}, {"_id": 0})
    if not doc:
        return None
    return {
        "username": doc.get("username", ""),
        "role": doc.get("role", ""),
        "password_hash": doc.get("password_hash", ""),
        "password_salt": doc.get("password_salt", ""),
        "is_active": bool(doc.get("is_active", 0)),
        "manager_username": doc.get("manager_username") or "",
        "department": doc.get("department") or "",
    }


def create_user(
    username: str,
    password: str,
    role: str,
    manager_username: str = "",
    department: str = "",
) -> tuple[bool, str]:
    username = username.strip().lower()
    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password) < 8:
        return False, "Password must be at least 8 characters."

    salt = generate_salt()
    password_hash = hash_password(password, salt)
    mgr = manager_username.strip() if manager_username and manager_username.strip() else None
    dept = department.strip() if department and department.strip() else None
    try:
        db = get_db()
        db["users"].insert_one(
            {
                "username": username,
                "role": role,
                "password_hash": password_hash,
                "password_salt": salt,
                "manager_username": mgr,
                "department": dept,
                "is_active": 1,
                "created_at": datetime.now().isoformat(),
            }
        )
    except DuplicateKeyError:
        return False, "Username already exists."
    log_audit(
        "CREATE_USER",
        "user",
        username,
        f"Role={role};Manager={manager_username or '-'};Dept={department or '-'}",
    )
    return True, "User created successfully."


def fetch_users() -> pd.DataFrame:
    db = get_db()
    docs = list(
        db["users"]
        .find({}, {"username": 1, "role": 1, "manager_username": 1, "department": 1, "is_active": 1, "created_at": 1})
        .sort("username", 1)
    )
    if not docs:
        return pd.DataFrame(columns=["id", "username", "role", "manager_username", "department", "is_active", "created_at"])
    for d in docs:
        d["id"] = str(d.pop("_id"))
    users_df = pd.DataFrame(docs)
    users_df["is_active"] = users_df["is_active"].map({1: "Yes", 0: "No"}).fillna("No")
    return users_df


def fetch_team_usernames(manager_username: str) -> list[str]:
    db = get_db()
    docs = db["users"].find({"manager_username": manager_username, "is_active": 1}, {"username": 1})
    return [d.get("username", "") for d in docs]


def get_visible_scorecards_for_current_user(**filters: str | None) -> pd.DataFrame:
    role = st.session_state.role
    username = st.session_state.username
    user_dept = (st.session_state.get("user_department") or "").strip()
    eff_department = filters.get("department")
    if role in ("Employee", "Manager") and user_dept and not eff_department:
        eff_department = user_dept
    df = fetch_scorecards(
        department=eff_department,
        role=filters.get("role"),
        review_cycle=filters.get("review_cycle"),
        status=filters.get("status"),
    )
    if df.empty:
        return df
    if role == "Admin":
        return df
    if role == "Viewer":
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


KPI_PRIORITY_OPTIONS = ["P1", "P2", "P3"]
KPI_FREQUENCY_OPTIONS = ["Daily", "Weekly", "Monthly", "Quarterly", "Annual", "Per Deal"]
KPI_TRACKING_OPTIONS = ["Auto", "Achieved", "On Track", "At Risk", "Behind", "Not Set"]


def derive_kpi_status(target: str, current: str) -> str:
    cur = (current or "").strip()
    if not cur:
        return "Not Set"
    tgt = (target or "").strip()
    tl = tgt.lower()
    if "zero" in tl or tl == "zero":
        cl = cur.strip().lower()
        if cl in ("0", "zero", "none", "no"):
            return "Achieved"
        return "Behind"
    nums_t = re.findall(r"[\d.]+", tgt.replace(",", ""))
    nums_c = re.findall(r"[\d.]+", cur.replace(",", ""))
    if nums_t and nums_c:
        try:
            t = float(nums_t[0])
            c = float(nums_c[0])
            if "<=" in tgt or bool(re.search(r"<\s*\d", tgt)):
                if c <= t:
                    return "Achieved"
                return "At Risk" if c <= t * 1.2 else "Behind"
            if ">=" in tgt or "≥" in tgt or "> " in tgt:
                if c >= t:
                    return "Achieved"
                return "At Risk" if c >= t * 0.9 else "Behind"
            if "%" in tgt or "%" in cur:
                if c >= t * 0.98:
                    return "Achieved"
                return "At Risk" if c >= t * 0.85 else "Behind"
        except ValueError:
            pass
    return "On Track"


def fetch_kpi_overrides() -> Dict[tuple[str, str, str], Dict[str, str | None]]:
    out: Dict[tuple[str, str, str], Dict[str, str | None]] = {}
    db = get_db()
    docs = db["kpi_registry_overrides"].find(
        {},
        {"department": 1, "role": 1, "metric": 1, "current_value": 1, "priority": 1, "frequency": 1, "status_override": 1},
    )
    for d in docs:
        out[(d.get("department", ""), d.get("role", ""), d.get("metric", ""))] = {
            "current_value": d.get("current_value") or "",
            "priority": d.get("priority") or "P2",
            "frequency": d.get("frequency") or "Monthly",
            "status_override": d.get("status_override"),
        }
    return out


def upsert_kpi_registry_row(
    department: str,
    role: str,
    metric: str,
    current_value: str,
    priority: str,
    frequency: str,
    status_override: str | None,
) -> None:
    ts = datetime.now().isoformat()
    so = status_override if status_override and status_override != "Auto" else None
    db = get_db()
    db["kpi_registry_overrides"].update_one(
        {"department": department, "role": role, "metric": metric},
        {
            "$set": {
                "current_value": current_value,
                "priority": priority,
                "frequency": frequency,
                "status_override": so,
                "updated_at": ts,
            },
            "$setOnInsert": {"department": department, "role": role, "metric": metric},
        },
        upsert=True,
    )
    log_audit(
        "KPI_REGISTRY_UPSERT",
        "kpi_registry",
        f"{department}:{role}:{metric}",
        "Registry row saved",
    )


def style_kpi_registry_display(display_df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """Color-code Status column (Achieved / On Track / At Risk / Behind / Not Set)."""
    styles = {
        "Achieved": "background-color: #d1fae5; color: #065f46; font-weight: 600; border-radius: 6px;",
        "On Track": "background-color: #dbeafe; color: #1e40af; font-weight: 600; border-radius: 6px;",
        "At Risk": "background-color: #fef3c7; color: #92400e; font-weight: 600; border-radius: 6px;",
        "Behind": "background-color: #fee2e2; color: #b91c1c; font-weight: 600; border-radius: 6px;",
        "Not Set": "background-color: #f3f4f6; color: #374151; font-weight: 600; border-radius: 6px;",
    }

    def _color(val: object) -> str:
        return styles.get(str(val), "background-color: #f9fafb; color: #111827; font-weight: 500;")

    styler = display_df.style
    if hasattr(styler, "map"):
        return styler.map(_color, subset=["Status"])
    return styler.applymap(_color, subset=["Status"])


def build_kpi_registry_df(department: str, overrides: Dict[tuple[str, str, str], Dict[str, str | None]]) -> pd.DataFrame:
    rows: List[Dict[str, str]] = []
    for role, kpis in DEPARTMENTS[department]["roles"].items():
        for k in kpis:
            key = (department, role, k["metric"])
            o = overrides.get(key, {})
            current = str(o.get("current_value") or "")
            priority = str(o.get("priority") or "P2")
            frequency = str(o.get("frequency") or "Monthly")
            raw_so = o.get("status_override")
            tracking = "Auto" if raw_so in (None, "") else str(raw_so)
            if tracking == "Auto":
                status = derive_kpi_status(str(k["target"]), current)
            else:
                status = tracking
            rows.append(
                {
                    "KPI Name": k["metric"],
                    "Category": k["category"],
                    "Owner": role,
                    "Target": k["target"],
                    "Current": current,
                    "Status": status,
                    "Priority": priority if priority in KPI_PRIORITY_OPTIONS else "P2",
                    "Frequency": frequency if frequency in KPI_FREQUENCY_OPTIONS else "Monthly",
                    "Tracking": tracking if tracking in KPI_TRACKING_OPTIONS else "Auto",
                    "_dept": department,
                    "_role": role,
                    "_metric": k["metric"],
                }
            )
    return pd.DataFrame(rows)


def kpi_management_page() -> None:
    st.markdown(
        '<div class="kpi-mgmt-header"><span style="font-size:1.35rem;font-weight:700;color:#0d2f8b;">KPI Management</span><br/>'
        '<span style="color:#4d5e8b;">Define live tracking for KPIs across departments. Editable fields apply to Admin and Manager roles.</span></div>',
        unsafe_allow_html=True,
    )

    h1, h2 = st.columns([3, 1])
    search_q = h1.text_input("Search", placeholder="Search KPIs or owners...", label_visibility="collapsed")
    h2.date_input("Period", value=date.today())
    overrides = fetch_kpi_overrides()

    dept_names = list(DEPARTMENTS.keys())
    _role = st.session_state.role
    _ud = (st.session_state.get("user_department") or "").strip()
    if _role in ("Employee", "Manager") and _ud and _ud in DEPARTMENTS:
        dept_names = [_ud]
    elif _role in ("Employee", "Manager") and _ud and _ud not in DEPARTMENTS:
        st.warning(
            f"Your profile department «{_ud}» is not in the KPI catalog. Contact an administrator."
        )
        dept_names = []
    if not dept_names:
        st.info("No department tabs to display.")
        return
    counts = {d: sum(len(v) for v in DEPARTMENTS[d]["roles"].values()) for d in dept_names}
    tab_labels = [f"{d} ({counts[d]})" for d in dept_names]
    tabs = st.tabs(tab_labels)
    can_edit = st.session_state.role in ("Admin", "Manager")

    for ti, dept in enumerate(dept_names):
        with tabs[ti]:
            base_df = build_kpi_registry_df(dept, overrides)
            if search_q.strip():
                q = search_q.strip().lower()
                mask = (
                    base_df["KPI Name"].str.lower().str.contains(q, na=False)
                    | base_df["Owner"].str.lower().str.contains(q, na=False)
                )
                df = base_df[mask].copy()
            else:
                df = base_df.copy()

            cats = sorted(df["Category"].unique().tolist()) if not df.empty else []
            stats = sorted(df["Status"].unique().tolist()) if not df.empty else []
            f1, f2 = st.columns(2)
            # Keys must be unique across all tabs (Streamlit runs every tab body each rerun).
            cat_pick = f1.multiselect(
                "Category filter",
                ["All"] + cats,
                default=["All"],
                key=f"kpi_mgmt_multiselect_category_{ti}",
            )
            stat_pick = f2.multiselect(
                "Status filter",
                ["All"] + stats,
                default=["All"],
                key=f"kpi_mgmt_multiselect_status_{ti}",
            )
            if "All" not in cat_pick and cat_pick:
                df = df[df["Category"].isin(cat_pick)]
            if "All" not in stat_pick and stat_pick:
                df = df[df["Status"].isin(stat_pick)]

            def _avg_score(s: str) -> float:
                m = {"Achieved": 5.0, "On Track": 4.0, "At Risk": 3.0, "Behind": 2.0, "Not Set": 0.0}
                return m.get(s, 3.0)

            n = len(df)
            achieved_n = int((df["Status"] == "Achieved").sum()) if n else 0
            risk_n = int(df["Status"].isin(["At Risk", "Behind"]).sum()) if n else 0
            avg_s = round(df["Status"].map(_avg_score).mean(), 2) if n else 0.0

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total KPIs", n)
            m2.metric("Achieved", achieved_n)
            m3.metric("At Risk / Behind", risk_n)
            m4.metric("Avg Score", f"{avg_s:.1f} / 5" if n else "—")

            show = df[
                [
                    "KPI Name",
                    "Category",
                    "Owner",
                    "Target",
                    "Current",
                    "Status",
                    "Priority",
                    "Frequency",
                    "Tracking",
                ]
            ].copy()

            legend_cols = st.columns(5)
            legend_items = [
                ("Achieved", "#d1fae5", "#065f46"),
                ("On Track", "#dbeafe", "#1e40af"),
                ("At Risk", "#fef3c7", "#92400e"),
                ("Behind", "#fee2e2", "#b91c1c"),
                ("Not Set", "#f3f4f6", "#374151"),
            ]
            for idx, (label, bg, fg) in enumerate(legend_items):
                legend_cols[idx].markdown(
                    f'<span style="display:inline-block;padding:4px 10px;border-radius:8px;'
                    f'background:{bg};color:{fg};font-size:0.78rem;font-weight:600">{label}</span>',
                    unsafe_allow_html=True,
                )

            st.caption("Registry overview — Status colors update after you save edits below.")
            if not show.empty:
                st.dataframe(
                    style_kpi_registry_display(show),
                    use_container_width=True,
                    hide_index=True,
                    height=min(520, 42 + len(show) * 38),
                )

            edited = None
            if can_edit:
                st.markdown("##### Edit tracking")
                edit_df = show.drop(columns=["Status"], errors="ignore")
                edited = st.data_editor(
                    edit_df,
                    column_config={
                        "KPI Name": st.column_config.TextColumn("KPI Name", disabled=True),
                        "Category": st.column_config.TextColumn(disabled=True),
                        "Owner": st.column_config.TextColumn("Owner", disabled=True),
                        "Target": st.column_config.TextColumn("Target", disabled=True),
                        "Current": st.column_config.TextColumn("Current", disabled=False),
                        "Priority": st.column_config.SelectboxColumn(
                            "Priority", options=KPI_PRIORITY_OPTIONS, disabled=False
                        ),
                        "Frequency": st.column_config.SelectboxColumn(
                            "Frequency", options=KPI_FREQUENCY_OPTIONS, disabled=False
                        ),
                        "Tracking": st.column_config.SelectboxColumn(
                            "Tracking",
                            options=KPI_TRACKING_OPTIONS,
                            disabled=False,
                            help="Auto = derive status from Target vs Current",
                        ),
                    },
                    hide_index=True,
                    use_container_width=True,
                    key=f"kpi_reg_editor_{dept}_{ti}",
                )

            exp = st.expander("Accessible to: Super Admin, Admin, Manager (edit). Others view-only.")
            exp.caption("Master KPI definitions come from the EPMS catalog; Current / Priority / Frequency persist in the database.")

            if can_edit and edited is not None and st.button("Save changes", key=f"save_kpi_{dept}_{ti}", type="primary"):
                for _, row in edited.iterrows():
                    tr = str(row["Tracking"])
                    so = None if tr == "Auto" else tr
                    upsert_kpi_registry_row(
                        dept,
                        str(row["Owner"]),
                        str(row["KPI Name"]),
                        str(row["Current"]),
                        str(row["Priority"]),
                        str(row["Frequency"]),
                        so,
                    )
                st.success("KPI registry updated.")
                st.rerun()

            csv_out = df.drop(columns=["_dept", "_role", "_metric"], errors="ignore").to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Export filtered (CSV)",
                data=csv_out,
                file_name=f"kpi_registry_{dept.replace(' ', '_')}.csv",
                mime="text/csv",
                key=f"dl_csv_{dept}_{ti}",
            )

            wdf = pd.DataFrame(
                {"Category": list(CATEGORY_WEIGHTS.keys()), "Weight (%)": list(CATEGORY_WEIGHTS.values())}
            )
            fig = px.bar(
                wdf,
                x="Weight (%)",
                y="Category",
                orientation="h",
                title="KPI category weightage (universal evaluation)",
                color="Weight (%)",
                color_continuous_scale="Blues",
            )
            fig.update_layout(showlegend=False, height=320, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig, use_container_width=True, key=f"kpi_mgmt_weights_{ti}")


def set_user_status(username: str, is_active: bool) -> None:
    db = get_db()
    db["users"].update_one({"username": username}, {"$set": {"is_active": 1 if is_active else 0}})
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
    db = get_db()
    db["users"].update_one({"username": username}, {"$set": {"password_hash": password_hash, "password_salt": salt}})
    log_audit("RESET_PASSWORD", "user", username, "Password reset by admin.")
    return True, "Password reset successfully."


def initialize_session() -> None:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "username" not in st.session_state:
        st.session_state.username = ""
    if "role" not in st.session_state:
        st.session_state.role = ""
    if "user_department" not in st.session_state:
        st.session_state.user_department = ""


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
                st.session_state.user_department = str(user.get("department") or "")
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
            dept_options = [""] + list(DEPARTMENTS.keys())
            user_department = st.selectbox(
                "Department (optional scope for Employee/Manager)",
                dept_options,
                help="If set, KPI Management and scorecard lists are limited to this department.",
            )
            create_submit = st.form_submit_button("Create User", use_container_width=True)
        if create_submit:
            assigned_manager = manager_mapping if new_role == "Employee" else ""
            ok, message = create_user(
                new_username,
                new_password,
                new_role,
                assigned_manager,
                user_department,
            )
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

    with st.expander("Email (SMTP / AWS SES SMTP)", expanded=False):
        st.caption(
            "Configure SMTP via environment variables. Recommended: AWS SES SMTP credentials. "
            "Required: EPMS_SMTP_HOST, EPMS_SMTP_PORT, EPMS_EMAIL_FROM, EPMS_SMTP_USERNAME, EPMS_SMTP_PASSWORD."
        )
        to_email = st.text_input("To", placeholder="recipient@example.com", key="email_to")
        subject = st.text_input("Subject", value="EPMS Test Email", key="email_subject")
        body = st.text_area("Message", value="Hello from EPMS.", key="email_body")
        if st.button("Send test email", type="primary", use_container_width=True, key="email_send_btn"):
            ok, msg = send_email_smtp(to_email=to_email, subject=subject, body=body)
            if ok:
                st.success(msg)
                log_audit("SEND_EMAIL", "email", to_email, f"Subject={subject}")
            else:
                st.error(msg)


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
        edit_record = fetch_scorecard_by_id(str(selected_id))
        if not edit_record:
            st.error("Selected record not found.")
            return
        if role == "Employee" and edit_record["created_by"] != username:
            st.error("You can only edit your own records.")
            return

    departments = list(DEPARTMENTS.keys())
    ud = (st.session_state.get("user_department") or "").strip()
    if role in ("Employee", "Manager") and ud and ud in DEPARTMENTS:
        departments = [ud]
    c1, c2 = st.columns(2)
    default_department = edit_record["department"] if edit_record else departments[0]
    if default_department not in departments:
        default_department = departments[0]
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
                scorecard_id=str(edit_record["id"]),
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
            st.success("Scorecard saved successfully. Data is persisted and visible in Reports.")


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
        update_scorecard_workflow(str(selected_id), next_status, manager_comment.strip())
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
    dept_note = (st.session_state.get("user_department") or "").strip()
    sidebar_user = f"User: {st.session_state.username} ({st.session_state.role})"
    if dept_note:
        sidebar_user += f" · Dept: {dept_note}"
    st.sidebar.caption(sidebar_user)
    st.sidebar.caption(f"DB Backend: {DB_BACKEND}")

    allowed_pages_by_role = {
        "Admin": [
            "Dashboard",
            "KPI Management",
            "Scorecard Entry",
            "Review Workflow",
            "Calibration",
            "Cycle Controls",
            "Reports",
            "User Management",
        ],
        "Manager": ["Dashboard", "KPI Management", "Scorecard Entry", "Review Workflow", "Calibration", "Reports"],
        "Employee": ["Dashboard", "KPI Management", "Scorecard Entry", "Reports"],
        "Viewer": ["Dashboard", "KPI Management", "Reports"],
    }
    pages = allowed_pages_by_role.get(st.session_state.role, ["Dashboard"])
    page = st.sidebar.radio("Go to", pages)

    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.username = ""
        st.session_state.role = ""
        st.session_state.user_department = ""
        st.rerun()

    if page == "Dashboard":
        dashboard_page()
    elif page == "KPI Management":
        kpi_management_page()
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
