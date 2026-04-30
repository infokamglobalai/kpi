"""Shared SQLAlchemy engine for SQLite (local) and PostgreSQL (production)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from epms.db_adapter import build_database_config


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    db_path = Path(os.getenv("EPMS_DB_PATH", "epms.db"))
    cfg = build_database_config(db_path)
    kwargs: dict = {"pool_pre_ping": True}
    if cfg.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(cfg.database_url, **kwargs)


def dialect_name() -> str:
    return get_engine().dialect.name
