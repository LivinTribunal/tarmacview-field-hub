"""engine and session factory for the hub's registry - own postgres schema, no alembic."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings

FIELDHUB_SCHEMA = "fieldhub"


class Base(DeclarativeBase):
    """declarative base for fieldhub models."""


def _build_engine():
    """engine for the configured database url.

    sqlite (dev/tests) has no schemas, so the fieldhub schema is translated
    away; in-memory urls share one connection so every session sees the
    same database.
    """
    url = settings.database_url
    if not url.startswith("sqlite"):
        return create_engine(url)

    in_memory = url in ("sqlite://", "sqlite:///:memory:")
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool if in_memory else None,
    )
    return engine.execution_options(schema_translate_map={FIELDHUB_SCHEMA: None})


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """create the fieldhub schema (postgres) and registry tables if missing."""
    import app.models  # noqa: F401

    if engine.url.get_backend_name() != "sqlite":
        with engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {FIELDHUB_SCHEMA}"))
    Base.metadata.create_all(engine)


def get_db():
    """request-scoped session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
