"""
app/services/certificate_service.py
-----------------------------------
Service handling the business logic for processing individual certificates.

This orchestrates the database updates and the PDF generation service.
By separating this from the background worker, we keep the worker strictly
focused on loop management and session handling, while this service
encapsulates the exact state transitions for a single certificate.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.certificate import Certificate, CertificateStatus
from app.models.job import GenerationJob
from app.services.pdf_service import generate_certificate_pdf

logger = logging.getLogger(__name__)


def process_single_certificate(
    db: Session,
    certificate: Certificate,
    job: GenerationJob,
) -> bool:
    """
    Process a single certificate through its lifecycle.

    Flow:
    1. Update status to PROCESSING (with flush so it's visible in the transaction).
    2. Try to generate the PDF via pdf_service.
    3. If successful: update status to COMPLETED, save file_path.
    4. If failure: update status to FAILED, save error_message.
    5. Update completed_at timestamp.

    The transaction is NOT committed here. The background worker manages
    the commit to ensure that either the entire certificate update (including
    the job counter increments) succeeds, or it rolls back cleanly.

    Args:
        db: The SQLAlchemy Session.
        certificate: The Certificate ORM model to process.
        job: The parent GenerationJob ORM model (for metadata).

    Returns:
        bool: True if generation was successful, False if it failed.
    """
    settings = get_settings()

    # 1. Mark as PROCESSING
    certificate.status = CertificateStatus.PROCESSING
    db.flush()  # Push the status update to the DB (but don't commit yet)

    # 2. Determine output directory: generated/<job_id>
    # We group certificates by job ID in the filesystem to avoid clutter.
    output_dir = settings.generated_files_path / str(job.id)

    try:
        # 3. Generate the PDF
        file_path = generate_certificate_pdf(
            recipient_name=certificate.recipient_name,
            certificate_title=job.certificate_title,
            course_name=job.course_name,
            organization=job.organization,
            issue_date=job.issue_date,
            certificate_id=str(certificate.id),
            output_dir=output_dir,
        )

        # 4. Success: Update certificate record
        certificate.status = CertificateStatus.COMPLETED
        certificate.file_path = file_path
        certificate.error_message = None
        certificate.completed_at = datetime.now(timezone.utc)

        logger.info("Successfully generated certificate %s", certificate.id)
        return True

    except Exception as exc:
        # 5. Failure: Update certificate record
        # We catch a broad Exception because we MUST NOT let an individual
        # failure crash the entire batch.
        error_msg = f"{type(exc).__name__}: {str(exc)}"

        certificate.status = CertificateStatus.FAILED
        certificate.file_path = None
        certificate.error_message = error_msg
        certificate.completed_at = datetime.now(timezone.utc)

        logger.error(
            "Failed to generate certificate %s: %s",
            certificate.id,
            error_msg,
            exc_info=True,
        )
        return False
