"""
app/main.py
-----------
Application entry point.

This module:
  1. Creates the FastAPI application instance with a lifespan context.
  2. Configures Python logging.
  3. Verifies the database connection on startup.
  4. Ensures the generated-files directory exists.
  5. Mounts API routers (will be added in later phases).
  6. Exposes a /health liveness endpoint.

Lifespan vs @app.on_event
--------------------------
FastAPI deprecated @app.on_event("startup") in favour of the lifespan
context manager.  `lifespan` is an async context manager: code before
`yield` runs at startup, code after `yield` runs at shutdown.  This
makes startup/shutdown logic co-located and testable with a single fixture.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

import app.models  # noqa: F401 — registers all ORM models with Base.metadata
from app.api.certificates import router as certificates_router
from app.api.jobs import router as jobs_router
from app.core.config import configure_logging, get_settings
from app.core.database import Base, engine, verify_database_connection

logger = logging.getLogger(__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs startup logic before `yield`, shutdown logic after.

    Startup
    -------
    1. Configure logging (must happen first so subsequent log calls work).
    2. Verify the database is reachable.
    3. Create the generated-files directory if it doesn't exist.

    Shutdown
    --------
    4. Dispose the SQLAlchemy connection pool (closes all open connections
       gracefully instead of letting the OS reclaim them).
    """
    settings = get_settings()

    # 1 ── Logging ──────────────────────────────────────────────────────────────
    configure_logging(settings.LOG_LEVEL)
    logger.info("Starting Bulk Certificate Generator API")

    # 2 ── Database ─────────────────────────────────────────────────────────────
    logger.info("Verifying database connection…")
    try:
        verify_database_connection()
    except Exception as exc:  # noqa: BLE001
        # Log the error and re-raise so uvicorn exits with a non-zero code.
        # This is intentional: a server that cannot reach its database should
        # not start accepting requests.
        logger.critical("Database connection failed: %s", exc)
        raise

    # 3 ── Database tables ───────────────────────────────────────────────────────
    # create_all() is idempotent: it inspects the existing schema and only
    # creates tables that are missing.  It never drops or modifies existing
    # tables, so it is safe to call on every startup.
    #
    # Alternative: Alembic migrations give you a full audit trail of schema
    # changes and are the right choice for production teams.  For this
    # single-developer project create_all() is simpler and sufficient.
    logger.info("Creating database tables if they do not exist…")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ready")

    # 4 ── File storage ─────────────────────────────────────────────────────────
    generated_dir: Path = settings.generated_files_path
    generated_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Generated files directory: %s", generated_dir.resolve())

    logger.info("Application startup complete")

    # ── Hand control to the application ────────────────────────────────────────
    yield

    # 4 ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("Shutting down — disposing database connection pool")
    engine.dispose()
    logger.info("Shutdown complete")


# ── Application factory ────────────────────────────────────────────────────────

app = FastAPI(
    title="Bulk Certificate Generator API",
    description=(
        "A production-quality API that accepts a list of recipients, "
        "generates individual PDF certificates using a predefined template, "
        "tracks per-certificate and per-job status, and allows certificates "
        "to be downloaded.\n\n"
        "**Background processing**: certificate PDFs are generated "
        "asynchronously via FastAPI BackgroundTasks — the job-creation "
        "endpoint returns HTTP 202 immediately while generation proceeds "
        "in the background."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.include_router(jobs_router)
app.include_router(certificates_router)


# ── Health check ───────────────────────────────────────────────────────────────


@app.get(
    "/health",
    tags=["Health"],
    summary="Liveness probe",
    response_description="Service is alive",
)
async def health_check() -> dict[str, str]:
    """
    Returns HTTP 200 with a simple JSON payload.

    Intentionally does **not** check the database — that is the
    responsibility of a separate readiness probe.  Liveness only
    confirms the process is running and the event loop is alive.
    """
    return {"status": "ok", "service": "bulk-certificate-generator"}
