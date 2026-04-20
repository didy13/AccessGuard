from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from server.config import get_config


class Base(DeclarativeBase):
    pass


def _build_engine():
    cfg = get_config()
    connect_args = {"check_same_thread": False} if cfg.database_url.startswith("sqlite") else {}
    return create_engine(cfg.database_url, connect_args=connect_args)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """FastAPI dependency that yields a DB session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all_tables() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate() -> None:
    """Add new columns to existing tables without Alembic."""
    insp = inspect(engine)
    if "role_mappings" in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns("role_mappings")}
        if "entitlements_json" not in existing:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE role_mappings ADD COLUMN entitlements_json TEXT NOT NULL DEFAULT '{}'"))
                conn.commit()
