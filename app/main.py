"""
app/main.py
-----------
Application entry point.

This module creates the FastAPI application instance and mounts the API
routers. In later phases we will add:
  - lifespan context (database table creation / connection pool warm-up)
  - global exception handlers
  - CORS middleware (if the Streamlit frontend is enabled)

For now it only exposes a health-check endpoint so we can verify the
server starts successfully after Phase 1.
"""

import logging

from fastapi import FastAPI

# ── Logger ─────────────────────────────────────────────────────────────────────
# We configure a module-level logger. The root log level will be set in
# Phase 2 once we have access to the Settings object.
logger = logging.getLogger(__name__)

# ── Application factory ────────────────────────────────────────────────────────
app = FastAPI(
    title="Bulk Certificate Generator API",
    description=(
        "A production-quality API that accepts a list of recipients, "
        "generates individual PDF certificates using a predefined template, "
        "tracks per-certificate and per-job status, and allows certificates "
        "to be downloaded."
    ),
    version="1.0.0",
    # OpenAPI tags will be populated by individual routers in later phases.
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"], summary="Liveness probe")
async def health_check() -> dict[str, str]:
    """
    Returns HTTP 200 with a simple JSON payload.

    Purpose
    -------
    - CI/CD pipelines use this to verify the container is alive.
    - Docker Compose HEALTHCHECK directive will call this endpoint.
    - Nothing else; it intentionally avoids database I/O so it stays fast
      even when the database is unavailable.
    """
    logger.info("Health check requested")
    return {"status": "ok", "service": "bulk-certificate-generator"}
