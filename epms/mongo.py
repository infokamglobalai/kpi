from __future__ import annotations

import os
from datetime import datetime
from functools import lru_cache

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from epms.auth import generate_salt, hash_password


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@lru_cache(maxsize=1)
def get_mongo_client() -> MongoClient:
    uri = os.getenv("EPMS_MONGODB_URI", "").strip()
    if not uri:
        raise RuntimeError("Missing EPMS_MONGODB_URI.")
    return MongoClient(uri, serverSelectionTimeoutMS=8000)


def get_db() -> Database:
    dbname = os.getenv("EPMS_MONGODB_DBNAME", "epms").strip() or "epms"
    return get_mongo_client()[dbname]


def _col(db: Database, name: str) -> Collection:
    return db.get_collection(name)


def init_mongo(
    review_cycles: list[str],
    default_admin_username: str,
    default_admin_password: str,
    log_audit_callback,
) -> None:
    db = get_db()

    # Users
    _col(db, "users").create_index([("username", ASCENDING)], unique=True, name="uniq_username")

    # Scorecards
    _col(db, "scorecards").create_index(
        [
            ("department", ASCENDING),
            ("role", ASCENDING),
            ("review_cycle", ASCENDING),
            ("status", ASCENDING),
            ("created_by", ASCENDING),
            ("created_at", DESCENDING),
        ],
        name="scorecards_filters",
    )
    _col(db, "scorecards").create_index([("created_at", DESCENDING)], name="scorecards_created_at")

    # Review cycles
    _col(db, "review_cycles").create_index([("cycle_name", ASCENDING)], unique=True, name="uniq_cycle_name")

    # Audit logs
    _col(db, "audit_logs").create_index([("created_at", DESCENDING)], name="audit_created_at")

    # KPI overrides
    _col(db, "kpi_registry_overrides").create_index(
        [("department", ASCENDING), ("role", ASCENDING), ("metric", ASCENDING)],
        unique=True,
        name="uniq_kpi_override",
    )

    # Seed cycles
    ts = datetime.now().isoformat()
    for cycle in review_cycles:
        _col(db, "review_cycles").update_one(
            {"cycle_name": cycle},
            {"$setOnInsert": {"cycle_name": cycle, "is_closed": 0, "updated_at": ts}},
            upsert=True,
        )

    # Seed default admin (optional)
    if _env_bool("EPMS_ENABLE_ADMIN_SEED", True):
        _seed_default_admin(db, default_admin_username, default_admin_password, log_audit_callback)


def _seed_default_admin(db: Database, username: str, password: str, log_audit_callback) -> None:
    username = (username or "").strip().lower()
    if not username:
        return

    existing = _col(db, "users").find_one({"username": username}, {"_id": 1})
    if existing:
        return

    salt = generate_salt()
    password_hash = hash_password(password, salt)
    _col(db, "users").insert_one(
        {
            "username": username,
            "role": "Admin",
            "password_hash": password_hash,
            "password_salt": salt,
            "manager_username": None,
            "department": None,
            "is_active": 1,
            "created_at": datetime.now().isoformat(),
        }
    )
    log_audit_callback("SEED_ADMIN", "user", username, "Default admin created.")

