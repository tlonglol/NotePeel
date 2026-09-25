"""Schema migration runner (Alembic).

    DATABASE_URL="<neon-pooled-url>" python -m scripts.migrate

Runs `alembic upgrade head` from backend/. Refuses to run against a database
that already has the app schema but no alembic_version table; such a database
must be stamped with the baseline first (one-time, see DECISIONS.md):

    alembic stamp 0001_baseline
"""
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect


def _url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    from app.config import get_settings
    return get_settings().database_url


def main() -> None:
    url = _url()
    insp = inspect(create_engine(url))
    tables = set(insp.get_table_names())
    if "users" in tables and "alembic_version" not in tables:
        sys.exit(
            "Refusing to migrate: schema exists but has no alembic_version table.\n"
            "Stamp the baseline once, then re-run:  alembic stamp 0001_baseline"
        )

    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    os.environ["DATABASE_URL"] = url
    command.upgrade(cfg, "head")
    print("✅ schema at head")


if __name__ == "__main__":
    main()
