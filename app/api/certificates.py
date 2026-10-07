"""
app/api/certificates.py
-----------------------
FastAPI router handling operations on individual certificates.

Phase 12: GET /api/certificates/{certificate_id}/download
"""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.certificate import Certificate, CertificateStatus

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/certificates",
    tags=["Certificates"],
)


@router.get(
    "/{certificate_id}/download",
    summary="Download a generated certificate",
    response_description="Returns the PDF file.",
    response_class=FileResponse,
)
def download_certificate(
    certificate_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """
    Download the generated PDF for a given certificate.

    Error cases handled:
    - 404: Certificate ID does not exist in the database.
    - 400: Certificate is still processing or failed.
    - 404: File is missing from the filesystem (e.g. accidentally deleted).
    """
    # 1. Fetch certificate from database
    cert = db.query(Certificate).filter(Certificate.id == certificate_id).first()

    if not cert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "CERTIFICATE_NOT_FOUND",
                    "message": f"Certificate with ID {certificate_id} does not exist.",
                }
            },
        )

    # 2. Check status
    if cert.status != CertificateStatus.COMPLETED:
        # If it failed, provide a hint. If pending/processing, tell them to wait.
        msg = (
            f"Cannot download. Certificate generation failed: {cert.error_message}"
            if cert.status == CertificateStatus.FAILED
            else f"Certificate is currently {cert.status}. Please check back later."
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "CERTIFICATE_NOT_READY", "message": msg}},
        )

    # 3. Check if file exists on disk
    if not cert.file_path:
        # This shouldn't happen if status is COMPLETED, but we guard against bad state.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "MISSING_FILE_PATH",
                    "message": "File path not found in database.",
                }
            },
        )

    # Using Path.resolve() helps ensure we aren't subject to directory traversal.
    # The file_path in the DB is stored as a relative path (e.g. "generated/uuid/cert.pdf").
    # We resolve it relative to the current working directory (where uvicorn is running).
    file_path = Path(cert.file_path).resolve()

    if not file_path.exists():
        logger.error(
            "Database says certificate %s is completed, but file %s is missing!",
            cert.id,
            file_path,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "FILE_MISSING",
                    "message": "The certificate file could not be found on the server.",
                }
            },
        )

    # 4. Return the file
    # FileResponse automatically handles streaming, Content-Length, and Content-Type (based on extension).
    # We set a nice filename so when the user clicks 'Download', it saves intuitively.
    filename = f"{cert.recipient_name.replace(' ', '_')}_Certificate.pdf"

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=filename,
    )
