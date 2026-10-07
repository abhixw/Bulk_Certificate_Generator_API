"""
app/schemas/certificate.py
--------------------------
Pydantic v2 response schemas for Certificate records.

These schemas define what the API returns to clients — they are completely
separate from the SQLAlchemy ORM model (app/models/certificate.py).

Separation of concerns
----------------------
ORM model  →  represents a database row, has SQLAlchemy column types,
               relationships, and lazy-loading behaviour.
Schema     →  represents a JSON payload, has string/int/UUID Python types,
               optional computed fields, and serialisation rules.

Never return an ORM model directly from a FastAPI route.  Always convert
via `Schema.model_validate(orm_obj)`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.certificate import CertificateStatus


class CertificateResponse(BaseModel):
    """
    Represents one certificate in a job's certificate listing.

    `from_attributes=True` (previously `orm_mode=True` in Pydantic v1)
    tells Pydantic to read values from object attributes rather than
    dictionary keys.  This is what enables `CertificateResponse.model_validate(cert)`
    where `cert` is a SQLAlchemy ORM instance.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique certificate identifier")

    recipient_name: str = Field(description="Full name of the certificate recipient")
    recipient_email: str = Field(description="Email address of the recipient")

    status: CertificateStatus = Field(
        description="Current lifecycle status of this certificate"
    )

    error_message: str | None = Field(
        default=None,
        description=(
            "Human-readable error description. Only present when status is FAILED."
        ),
    )

    download_url: str | None = Field(
        default=None,
        description=(
            "URL to download the generated PDF. Only present when status is COMPLETED."
        ),
    )

    created_at: datetime = Field(
        description="Timestamp when this certificate was created"
    )
    updated_at: datetime = Field(description="Timestamp of the last status change")
    completed_at: datetime | None = Field(
        default=None,
        description="Timestamp when generation succeeded or failed",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "recipient_name": "Abhinav Shrimali",
                "recipient_email": "abhinav@example.com",
                "status": "COMPLETED",
                "error_message": None,
                "download_url": "/api/certificates/3fa85f64-5717-4562-b3fc-2c963f66afa6/download",
                "created_at": "2026-10-07T10:00:00Z",
                "updated_at": "2026-10-07T10:00:05Z",
                "completed_at": "2026-10-07T10:00:05Z",
            }
        },
    )
