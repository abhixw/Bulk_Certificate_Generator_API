"""
app/models/certificate.py
--------------------------
SQLAlchemy 2.x ORM model for an individual certificate within a bulk job.

Each Certificate represents one recipient.  Its lifecycle is managed by the
background worker independently — a failure in one Certificate never affects
the others.

State machine
-------------
    Job is created → │ PENDING │
                      └────┬────┘
                            │ worker picks this certificate up
                      ┌─────▼─────┐
                      │ PROCESSING│
                      └─────┬─────┘
                             │
                    ┌────────┴────────┐
                    │ success         │ exception
              ┌─────▼──────┐   ┌─────▼──────┐
              │  COMPLETED │   │   FAILED   │
              └────────────┘   └────────────┘
"""

import enum
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# ── Status enum ────────────────────────────────────────────────────────────────


class CertificateStatus(str, enum.Enum):
    """
    Lifecycle states for a single Certificate record.

    Inherits from str for the same reason as JobStatus:
    Pydantic serialises it as a plain string automatically.
    """

    PENDING = "PENDING"
    """Waiting for the background worker to reach this certificate."""

    PROCESSING = "PROCESSING"
    """PDF generation is in progress for this recipient."""

    COMPLETED = "COMPLETED"
    """PDF generated and saved.  file_path is set."""

    FAILED = "FAILED"
    """PDF generation raised an exception.  error_message is set."""


# ── ORM model ──────────────────────────────────────────────────────────────────


class Certificate(Base):
    """
    Persists the per-recipient certificate record.

    Columns
    -------
    id               : UUID primary key.
    job_id           : Foreign key → generation_jobs.id.
    recipient_name   : Submitted recipient name (stored for audit trail).
    recipient_email  : Submitted recipient email.
    status           : Current lifecycle state (see CertificateStatus).
    file_path        : Relative path to the generated PDF on the filesystem.
                       NULL until status = COMPLETED.
    error_message    : Human-readable error description.
                       NULL unless status = FAILED.
    created_at       : Set by DB at INSERT.
    updated_at       : Auto-bumped on every UPDATE.
    completed_at     : Set when status reaches COMPLETED or FAILED.

    Why store file_path instead of the PDF bytes?
    -----------------------------------------------
    Storing binary blobs in PostgreSQL is possible (BYTEA / Large Objects)
    but has significant drawbacks:
      - Bloats the database backup size.
      - Cannot be served directly by a web server (nginx) without reading
        through the application.
      - Makes it impossible to move to object storage (S3 / R2) later
        without a data migration.
    Storing only the path decouples the database from the file layer entirely.
    """

    __tablename__ = "certificates"

    # ── Table-level constraints / indexes ───────────────────────────────────────
    __table_args__ = (
        # Composite index: "give me all certificates for job X with status Y"
        # — used by the progress query and the listing endpoint.
        sa.Index("ix_certificates_job_id_status", "job_id", "status"),
    )

    # ── Primary key ────────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── Foreign key ────────────────────────────────────────────────────────────
    job_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey(
            "generation_jobs.id",
            # If the parent job is deleted, cascade-delete all its certificates.
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,  # standalone index for "all certs for this job" queries
    )

    # ── Recipient data ─────────────────────────────────────────────────────────
    recipient_name: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )

    recipient_email: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
        index=True,  # allows fast lookup by email if needed in future
    )

    # ── Status ─────────────────────────────────────────────────────────────────
    status: Mapped[CertificateStatus] = mapped_column(
        sa.Enum(CertificateStatus, native_enum=False, length=20),
        default=CertificateStatus.PENDING,
        nullable=False,
    )

    # ── Output / error ─────────────────────────────────────────────────────────
    file_path: Mapped[str | None] = mapped_column(
        sa.String(512),
        nullable=True,
        default=None,
        comment="Relative path to the generated PDF. Set when status=COMPLETED.",
    )

    error_message: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
        default=None,
        comment="Human-readable error description. Set when status=FAILED.",
    )

    # ── Timestamps ─────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # ── Relationship ────────────────────────────────────────────────────────────
    job: Mapped["GenerationJob"] = relationship(  # noqa: F821
        "GenerationJob",
        back_populates="certificates",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Certificate id={self.id} "
            f"recipient={self.recipient_email!r} "
            f"status={self.status}>"
        )
