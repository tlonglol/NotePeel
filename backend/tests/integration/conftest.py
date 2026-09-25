"""Postgres-backed integration tests.

Skipped unless TEST_DATABASE_URL is set (or backend/.env.test exists). CI
provides a pgvector/pgvector container; locally point it at the notepeel_test
database on Neon or a compose Postgres. The schema is brought to Alembic head
once per session. Each test gets its own throwaway user and cleans up after.
"""
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _test_url():
    if os.environ.get("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]
    env_test = BACKEND_DIR / ".env.test"
    if env_test.exists():
        for line in env_test.read_text().splitlines():
            if line.startswith("TEST_DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    return None


TEST_URL = _test_url()
requires_pg = pytest.mark.skipif(TEST_URL is None, reason="TEST_DATABASE_URL not set")


@pytest.fixture(scope="session")
def pg_engine():
    if TEST_URL is None:
        pytest.skip("TEST_DATABASE_URL not set")
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    os.environ["DATABASE_URL"] = TEST_URL
    command.upgrade(cfg, "head")
    engine = create_engine(TEST_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def db(pg_engine):
    session = sessionmaker(bind=pg_engine)()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def user(db, pg_engine):
    """A throwaway user; everything it owns is deleted afterwards."""
    from app.models.user import User
    tag = uuid.uuid4().hex[:10]
    u = User(email=f"itest-{tag}@notepeel.local", username=f"itest_{tag}",
             hashed_password="x", is_active=False)
    db.add(u)
    db.commit()
    db.refresh(u)
    yield u
    db.rollback()
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM notes WHERE owner_id = :id"), {"id": u.id})
        conn.execute(text("DELETE FROM notebooks WHERE owner_id = :id"), {"id": u.id})
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": u.id})
