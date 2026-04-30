from __future__ import annotations

from pathlib import Path

from epms.mongo import init_mongo


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
    # SQL backends are no longer used at runtime; MongoDB is the source of truth.
    del db_path
    init_mongo(
        review_cycles=review_cycles,
        default_admin_username=default_admin_username,
        default_admin_password=default_admin_password,
        log_audit_callback=log_audit_callback,
    )
