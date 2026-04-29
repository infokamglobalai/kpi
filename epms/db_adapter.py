from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatabaseConfig:
    backend: str
    database_url: str


def build_database_config(default_sqlite_path: Path) -> DatabaseConfig:
    """
    Build DB config from environment.

    Priority:
    1) EPMS_DATABASE_URL (supports postgresql+psycopg2://... and sqlite:///...)
    2) EPMS_DB_PATH (local sqlite file)
    """
    explicit_url = os.getenv("EPMS_DATABASE_URL", "").strip()
    if explicit_url:
        backend = "postgresql" if explicit_url.startswith("postgresql") else "sqlite"
        return DatabaseConfig(backend=backend, database_url=explicit_url)

    sqlite_path = Path(os.getenv("EPMS_DB_PATH", str(default_sqlite_path)))
    sqlite_url = f"sqlite:///{sqlite_path.as_posix()}"
    return DatabaseConfig(backend="sqlite", database_url=sqlite_url)


def is_postgres_configured(default_sqlite_path: Path) -> bool:
    return build_database_config(default_sqlite_path).backend == "postgresql"
