"""
app/workers/certificate_worker.py
----------------------------------
Background worker that processes a generation job.

This module is triggered by FastAPI's BackgroundTasks. It runs in a separate
thread after the HTTP response has been sent to the client.

Key Responsibilities:
1. Session Management: Opens and closes its own SQLAlchemy Session.
2. Job State: Transitions the job from PENDING -> PROCESSING -> COMPLETED.
3. Looping: Iterates over all certificates, processing them sequentially.
4. Error Isolation: If one certificate fails, it catches the error, updates
   that certificate's status, and continues to the next one.
5. Atomic Commits: Commits after each certificate to ensure progress is
   saved immediately (so the progress endpoint reflects real-time status).
"""

import logging
import uuid
from datetime import datetime, timezone

from app.core.database import SessionLocal
from app.models.certificate import Certificate, CertificateStatus
from app.models.job import GenerationJob, JobStatus
from app.services.certificate_service import process_single_certificate

logger = logging.getLogger(__name__)


def process_job(job_id: uuid.UUID) -> None:
    """
    Entry point for the background worker.

    Args:
        job_id: The UUID of the GenerationJob to process.
    """
    logger.info("Background worker started for job %s", job_id)

    # 1. Open our own database session.
    # The request that triggered this task has already finished, meaning its
    # session (yielded by get_db) is closed. We MUST create a new one.
    db = SessionLocal()

    try:
        # 2. Load the job
        job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        if not job:
            logger.error("Job %s not found in database. Worker aborting.", job_id)
            return

        # 3. Mark job as PROCESSING
        job.status = JobStatus.PROCESSING
        db.commit()

        # Load all PENDING certificates for this job
        certificates = (
            db.query(Certificate)
            .filter(Certificate.job_id == job_id)
            .filter(Certificate.status == CertificateStatus.PENDING)
            .all()
        )

        logger.info(
            "Found %d certificates to process for job %s", len(certificates), job_id
        )

        # 4. Loop through certificates sequentially
        for cert in certificates:
            try:
                # Process the certificate (this sets status, file_path, error_message, etc.)
                # but does NOT commit.
                success = process_single_certificate(db, cert, job)

                # Update the job counters
                if success:
                    job.completed_count += 1
                else:
                    job.failed_count += 1

                # Commit the transaction for THIS certificate + job counter update.
                # This makes the progress visible to the GET /api/jobs/{id} endpoint immediately.
                db.commit()

            except Exception as e:
                # In theory, process_single_certificate catches all errors.
                # This outer try-except is a failsafe to ensure one disastrous error
                # (e.g. DB flush failure) doesn't break the loop.
                logger.error(
                    "Unexpected critical error processing certificate %s: %s",
                    cert.id,
                    e,
                    exc_info=True,
                )
                db.rollback()  # Rollback this iteration's transaction

                # Attempt to mark this cert as FAILED and continue
                try:
                    cert.status = CertificateStatus.FAILED
                    cert.error_message = "Unexpected critical worker error"
                    job.failed_count += 1
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.error(
                        "Could not save FAILED state for certificate %s", cert.id
                    )

        # 5. Finalize Job Status
        # After the loop, determine the final job state based on counts.
        if job.failed_count > 0:
            if job.completed_count > 0:
                job.status = JobStatus.COMPLETED_WITH_ERRORS
            else:
                # If everything failed, the job itself essentially failed
                job.status = JobStatus.FAILED
        else:
            job.status = JobStatus.COMPLETED

        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "Job %s finished. Status: %s. Completed: %d, Failed: %d",
            job.id,
            job.status,
            job.completed_count,
            job.failed_count,
        )

    except Exception as e:
        # 6. Fundamental System Error
        # If something goes catastrophically wrong (e.g. Neon connection drops completely),
        # we try to mark the whole job as FAILED.
        logger.critical(
            "Catastrophic error processing job %s: %s", job_id, e, exc_info=True
        )
        db.rollback()

        try:
            # Re-fetch the job in a fresh transaction just to mark it failed
            job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
            if job:
                job.status = JobStatus.FAILED
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            # If the database is completely unreachable, there's nothing more we can do
            pass

    finally:
        # 7. ALWAYS close the session to return the connection to the pool.
        db.close()
