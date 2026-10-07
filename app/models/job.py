"""
app/models/job.py
-----------------
SQLAlchemy 2.x ORM model for a certificate generation job.

A GenerationJob represents one bulk request.  It owns N Certificate records
(one per recipient).  Its status is derived from the aggregate status of its
certificates after the background worker finishes.

State machine
-------------
                  ┌─────────┐
    API creates → │ PENDING │
                  └────┬────┘
                       │ background worker picks it up
                  ┌────▼──────┐
                  │ PROCESSING│
                  └────┬──────┘
                       │
           ┌───────────┼──────────────┐
           │           │              │
    all OK │   some OK │ some FAILED  │ total system failure
           │           │              │
    ┌──────▼───┐  ┌────▼──────────┐ ┌▼──────┐
    │COMPLETED │  │COMPLETED_WITH │ │FAILED │
    └──────────┘  │    _ERRORS   │ └───────┘
                  └──────────────┘
"""

import enum
import uuid
from datetime import date, datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# ── Status enum ────────────────────────────────────────────────────────────────


class JobStatus(str, enum.Enum):
    """
    Lifecycle states for a GenerationJob.

    Why inherit from `str`?
    Inheriting from both str and Enum means each member IS a string.
    This lets Pydantic serialise the value directly (e.g. "PENDING")
    instead of the enum object, and allows direct string comparison
    in SQLAlchemy WHERE clauses.
    """

    PENDING = "PENDING"
    """Job created, not yet picked up by the background worker."""

    PROCESSING = "PROCESSING"
    """Background worker is actively generating certificates."""

    COMPLETED = "COMPLETED"
    """All certificates generated successfully."""

    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    """At least one certificate succeeded; at least one failed."""

    FAILED = "FAILED"
    """
    A fundamental system/database error prevented the job from being
    processed at all.  No individual certificate was generated.
    """


# ── ORM model ──────────────────────────────────────────────────────────────────


class GenerationJob(Base):
    """
    Persists a bulk certificate-generation request.

    Columns
    -------
    id               : UUID primary key — globally unique, generated in Python.
    status           : Current lifecycle state (see JobStatus).
    total_count      : Number of recipients submitted in the request.
    completed_count  : Certificates successfully generated so far.
    failed_count     : Certificates that encountered an error.
    created_at       : Timestamp set by the database server at INSERT time.
    updated_at       : Timestamp bumped automatically on every UPDATE.
    completed_at     : Set when the job reaches a terminal state.

    Why store counts redundantly?
    We could always compute counts with COUNT(*) queries on the certificates
    table.  Storing them directly on the job row lets the progress endpoint
    return data in a single indexed primary-key lookup — no joins, no
    aggregates, O(1) read regardless of batch size.
    """

    __tablename__ = "generation_jobs"

    # ── Primary key ────────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        primary_key=True,
        # Generate UUID in Python (not the DB) so we know the ID before the
        # INSERT completes — useful for building the response immediately.
        default=uuid.uuid4,
    )

    # ── Status ─────────────────────────────────────────────────────────────────
    status: Mapped[JobStatus] = mapped_column(
        # native_enum=False → store as VARCHAR rather than a PostgreSQL ENUM
        # type.  Adding a new status value with a native PG enum requires
        # ALTER TYPE which takes a lock.  VARCHAR + Python validation is
        # simpler and safer.
        sa.Enum(JobStatus, native_enum=False, length=30),
        default=JobStatus.PENDING,
        nullable=False,
        index=True,  # common WHERE clause: "find all PROCESSING jobs"
    )

    # ── Counts ─────────────────────────────────────────────────────────────────
    total_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
    )

    completed_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    failed_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # ── Job Metadata ───────────────────────────────────────────────────────────
    certificate_title: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )

    course_name: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )

    organization: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )

    issue_date: Mapped[date] = mapped_column(
        sa.Date,
        nullable=False,
    )

    # ── Timestamps ─────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        # server_default uses the database clock — avoids skew between
        # application servers in a multi-process deployment.
        server_default=sa.func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        # onupdate is a SQLAlchemy-level hook: SQLAlchemy sets this column to
        # the current UTC time whenever it emits an UPDATE for this row.
        onupdate=lambda: datetime.now(timezone.utc),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # ── Relationship ────────────────────────────────────────────────────────────
    certificates: Mapped[list["Certificate"]] = relationship(  # noqa: F821
        "Certificate",
        back_populates="job",
        # lazy="select" means: don't load certificates when loading a job.
        # We always load them explicitly when needed (e.g. listing endpoint).
        # This prevents accidental N+1 queries.
        lazy="select",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<GenerationJob id={self.id} status={self.status} "
            f"total={self.total_count} completed={self.completed_count} "
            f"failed={self.failed_count}>"
        )
