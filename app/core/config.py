"""
app/core/config.py
------------------
Centralised application settings.

Why pydantic-settings?
- Reads every field from environment variables OR a .env file automatically.
- Gives us type-checking and validation for free (e.g. DATABASE_URL cannot
  be an empty string).
- The single Settings object is the only place in the codebase that ever
  touches os.environ.  All other modules import `get_settings()`.

Why @lru_cache on get_settings()?
- Settings() reads and parses the .env file on every call.  Wrapping it
  in lru_cache makes it a singleton: the file is parsed exactly once for
  the lifetime of the process, and every module gets the same object.
- In tests we can call `get_settings.cache_clear()` before monkey-patching
  environment variables so each test starts with a fresh Settings instance.
"""

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All runtime configuration for the application.

    Field sources (in priority order, highest first):
      1. Actual environment variables  (e.g. export DATABASE_URL=...)
      2. Variables declared in the .env file
      3. Default values defined here

    This priority order means Docker / production deployments can override
    .env values simply by setting real environment variables.
    """

    model_config = SettingsConfigDict(
        # Look for a .env file relative to the current working directory
        # (the project root when running `uvicorn app.main:app`).
        env_file=".env",
        env_file_encoding="utf-8",
        # Silently ignore env vars that don't map to a Settings field.
        # Prevents errors when the shell has unrelated variables set.
        extra="ignore",
    )

    # ── Database ────────────────────────────────────────────────────────────────
    # Format (local):      postgresql+psycopg://user:pass@localhost:5432/certdb
    # Format (Neon):       postgresql+psycopg://user:pass@ep-xxx.neon.tech/certdb?sslmode=require
    #
    # The `postgresql+psycopg` dialect prefix tells SQLAlchemy to use the
    # psycopg 3 driver.  psycopg2 uses `postgresql+psycopg2`.
    DATABASE_URL: str

    # ── File storage ────────────────────────────────────────────────────────────
    # Where generated PDFs are saved.  Can be absolute or relative.
    # Relative paths are resolved from wherever uvicorn is launched (project root).
    GENERATED_FILES_DIR: str = "generated"

    # ── Logging ─────────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "info"

    # ── Validators ──────────────────────────────────────────────────────────────

    @field_validator("DATABASE_URL")
    @classmethod
    def database_url_must_use_psycopg3_dialect(cls, v: str) -> str:
        """
        Ensure the URL uses the psycopg 3 dialect prefix so SQLAlchemy
        selects the correct driver.  A common mistake is to copy a psycopg2
        URL (postgresql+psycopg2://...) or a plain postgres:// URL from Neon.
        """
        if not v.startswith(("postgresql+psycopg://", "postgresql+psycopg:")):
            raise ValueError(
                "DATABASE_URL must use the 'postgresql+psycopg' dialect "
                "(psycopg 3).  Example: "
                "postgresql+psycopg://user:pass@host:5432/dbname"
            )
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def log_level_must_be_valid(cls, v: str) -> str:
        valid = {"debug", "info", "warning", "error", "critical"}
        if v.lower() not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}")
        return v.upper()  # stdlib logging wants uppercase

    # ── Computed helpers ────────────────────────────────────────────────────────

    @property
    def generated_files_path(self) -> Path:
        """
        Returns GENERATED_FILES_DIR as a resolved Path object.

        Using Path() ensures cross-platform compatibility and lets callers
        use / operator for sub-paths (e.g. settings.generated_files_path / job_id).
        """
        return Path(self.GENERATED_FILES_DIR)


@lru_cache
def get_settings() -> Settings:
    """
    Returns the cached singleton Settings instance.

    Usage
    -----
    From any module::

        from app.core.config import get_settings
        settings = get_settings()

    In FastAPI dependency injection::

        from fastapi import Depends
        def my_endpoint(settings: Settings = Depends(get_settings)):
            ...

    In tests::

        from app.core.config import get_settings
        get_settings.cache_clear()        # force re-read after monkeypatching env
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://...")
        settings = get_settings()
    """
    return Settings()


def configure_logging(level: str) -> None:
    """
    Configure the root Python logger.

    Called once at application startup (lifespan).  All subsequent
    `logging.getLogger(__name__)` calls in other modules automatically
    inherit this level and format.

    We use basicConfig (not dictConfig) deliberately — it is simple,
    sufficient for a single-process application, and needs no extra
    dependencies.  A production deployment would replace this with
    structlog or similar.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
