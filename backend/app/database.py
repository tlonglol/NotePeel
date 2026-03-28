from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)
    _apply_safe_schema_updates()


def _apply_safe_schema_updates():
    """
    Apply lightweight schema repairs for local/dev databases when models gain
    new columns but no formal migration system is in place yet.
    """
    inspector = inspect(engine)
    if "notes" not in inspector.get_table_names():
        return

    note_columns = {column["name"] for column in inspector.get_columns("notes")}
    note_indexes = {index["name"] for index in inspector.get_indexes("notes")}

    with engine.begin() as connection:
        if "share_token" not in note_columns:
            connection.execute(text("ALTER TABLE notes ADD COLUMN share_token VARCHAR(36)"))
            note_columns.add("share_token")

        if "share_token" in note_columns and "ix_notes_share_token" not in note_indexes:
            connection.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS ix_notes_share_token ON notes (share_token)")
            )
