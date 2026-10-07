"""
app/core/database.py
--------------------
SQLAlchemy 2.x synchronous engine, session factory, and ORM Base.

Architecture decisions
----------------------

1.  Synchronous engine, not async
    We use `create_engine` (synchronous) rather than `create_async_engine`.
    FastAPI BackgroundTasks executes sync callables in a thread-pool, so our
    background worker can make blocking database calls safely.  Switching to
    async would require `AsyncSession`, `async with`, and `await` throughout
    the worker — significant complexity for no real throughput benefit in a
    single-process application.

2.  psycopg 3 dialect (`postgresql+psycopg`)
    psycopg 3 is the modern replacement for psycopg2.  It supports both sync
    and async, has a cleaner API, and is actively maintained.  The `[binary]`
    extra bundles pre-compiled C extensions so no system libpq-dev is needed.

3.  Connection pool
    SQLAlchemy maintains a pool of persistent database connections so each
    request/background-task does not pay TCP + TLS handshake overhead.
    - pool_size=5       : keep 5 connections open permanently
    - max_overflow=10   : allow up to 10 extra connections under burst load
    - pool_pre_ping=True: execute a cheap "SELECT 1" before reusing a
                         connection to detect and replace stale/dropped ones.
                         This is essential for cloud databases like Neon that
                         may close idle connections.

4.  expire_on_commit=False
    By default SQLAlchemy expires all ORM object attributes after a commit.
    This means accessing `obj.id` after `session.commit()` would trigger a
    SELECT.  Setting expire_on_commit=False prevents this, which is critical
    for background tasks where the session may not be alive to reload data.

5.  Session per request / per background task
    `get_db()` is a FastAPI dependency that yields a fresh Session for each
    HTTP request and closes it afterward.  Background tasks must NOT use this
    generator — they create their own Session with `SessionLocal()` directly,
    own it for the full duration of the task, and close it themselves.
    See: app/workers/certificate_worker.py
"""

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ── Engine ─────────────────────────────────────────────────────────────────────


def _build_engine():
    """
    Build the SQLAlchemy engine from the current Settings.

    Factored into a function (rather than module-level statement) so tests
    can call get_settings.cache_clear() + monkeypatch env vars before the
    engine is created with a test DATABASE_URL.
    """
    settings = get_settings()
    return create_engine(
        settings.DATABASE_URL,
        # Validate connections before handing them to the application.
        # Prevents "SSL connection has been closed unexpectedly" errors from
        # Neon's aggressive idle-connection timeouts.
        pool_pre_ping=True,
        # Permanent connections kept in the pool.
        pool_size=5,
        # Extra connections allowed beyond pool_size during traffic spikes.
        # Total max = pool_size + max_overflow = 15 concurrent connections.
        max_overflow=10,
        # Set to True to print every SQL statement — useful for debugging
        # but very noisy in production.
        echo=False,
    )


engine = _build_engine()

# ── Session factory ────────────────────────────────────────────────────────────

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    # Never auto-commit — we control transaction boundaries explicitly.
    autocommit=False,
    # Never auto-flush — we call session.flush() / session.commit() ourselves.
    autoflush=False,
    # See docstring note 4 above.
    expire_on_commit=False,
)

# ── Declarative base ───────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    """
    All SQLAlchemy ORM models inherit from this class.

    Why DeclarativeBase (SQLAlchemy 2.x) instead of declarative_base()?
    - `declarative_base()` is the SQLAlchemy 1.x API (still works but
      deprecated in 2.x).
    - `DeclarativeBase` is the idiomatic 2.x approach: it's a plain class,
      supports type annotations on columns (Mapped[]), and integrates with
      Pydantic's type system cleanly.
    """

    pass


# ── FastAPI dependency ─────────────────────────────────────────────────────────


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database Session for the duration of
    one HTTP request.

    Usage in a route::

        @router.post("/jobs/")
        def create_job(db: Session = Depends(get_db)):
            ...

    The `try / finally` guarantees the session is always closed even if the
    route handler raises an exception.  SQLAlchemy rolls back any uncommitted
    transaction automatically when a Session is closed.

    IMPORTANT: Never pass this session to a BackgroundTask.  By the time the
    background function runs, the `finally` block has already closed the
    session.  Background tasks must open their own session via SessionLocal().
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Health helper ──────────────────────────────────────────────────────────────


def verify_database_connection() -> None:
    """
    Executes a lightweight query to confirm the database is reachable.

    Called once at application startup (lifespan).  Raises an exception if
    the connection cannot be established, which causes uvicorn to exit with a
    non-zero code — immediately visible in Docker logs or CI output instead
    of failing silently on the first real request.
    """
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Database connection verified successfully")
