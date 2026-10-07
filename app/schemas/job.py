"""
app/schemas/job.py
------------------
Pydantic v2 schemas for the job lifecycle:

  CreateJobRequest     →  validated input from the client
  RecipientInput       →  nested input model for one recipient
  CreateJobResponse    →  HTTP 202 response body after job creation
  JobStatusResponse    →  GET /api/jobs/{id} response
  JobCertificatesResponse → GET /api/jobs/{id}/certificates response

Validation responsibilities
----------------------------
All REQUEST validation lives here.  If ANY field fails validation,
FastAPI returns a 422 Unprocessable Entity before a database record
is created.  This is distinct from INDIVIDUAL CERTIFICATE FAILURE,
which happens after the job has already been persisted and processing
has begun.

Rule of thumb
-------------
  Pydantic schema rejects bad input  →  HTTP 4xx, no DB record created
  Certificate service catches an error →  certificate.status = FAILED,
                                          job continues
"""

from __future__ import annotations

import re
import uuid
from datetime import date

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from app.models.job import JobStatus

# ── Email validation ────────────────────────────────────────────────────────────
# We use a deliberately simple regex rather than adding the `email-validator`
# package as a dependency.  For a public API you would use `pydantic[email]`
# (which uses the RFC 5321-compliant `email-validator` library), but for this
# project the regex covers all realistic inputs without the extra dependency.
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

# ── Constants ──────────────────────────────────────────────────────────────────
MAX_RECIPIENTS = 500


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────


class RecipientInput(BaseModel):
    """
    Represents a single recipient submitted by the client.

    Validators (applied in declaration order)
    -----------------------------------------
    1. `name`  : stripped of leading/trailing whitespace, must be non-empty.
    2. `email` : stripped, lowercased, must match a basic email pattern.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Full name of the certificate recipient. Cannot be empty.",
        examples=["Abhinav Shrimali"],
    )

    email: str = Field(
        ...,
        min_length=5,
        max_length=255,
        description="Valid email address of the recipient.",
        examples=["abhinav@example.com"],
    )

    @field_validator("name", mode="before")
    @classmethod
    def strip_and_validate_name(cls, v: object) -> str:
        """
        Strip whitespace then let min_length catch the empty-string case.

        Using `mode='before'` means this runs BEFORE Pydantic's own type
        coercion.  This ensures " " (whitespace-only) is caught by min_length
        after stripping rather than being accepted as a valid non-empty string.
        """
        if isinstance(v, str):
            return v.strip()
        return v  # type: ignore[return-value]  # Pydantic will reject non-str

    @field_validator("email", mode="before")
    @classmethod
    def normalise_and_validate_email(cls, v: object) -> str:
        """
        Strip + lowercase the email before pattern validation.

        Lowercasing is important for the duplicate-email check in
        CreateJobRequest: 'User@Example.com' and 'user@example.com'
        must be treated as the same address.
        """
        if isinstance(v, str):
            v = v.strip().lower()
            if not _EMAIL_RE.match(v):
                raise ValueError(f"'{v}' is not a valid email address")
            return v
        return v  # type: ignore[return-value]


class CreateJobRequest(BaseModel):
    """
    Body of POST /api/jobs/

    Validation rules (enforced by Pydantic before any DB access)
    -------------------------------------------------------------
    - certificate_title, course_name, organization: non-empty strings
    - issue_date: valid ISO 8601 date (e.g. "2026-10-07")
    - recipients:
        * list cannot be empty              → min_length=1
        * list cannot exceed 500 entries    → max_length=MAX_RECIPIENTS
        * each recipient passes RecipientInput validation
        * no two recipients share the same email (case-insensitive)
    """

    certificate_title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Title printed on the certificate (e.g. 'Certificate of Completion').",
        examples=["Certificate of Completion"],
    )

    course_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the course or event.",
        examples=["Python Backend Development"],
    )

    organization: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the issuing organisation.",
        examples=["ABC Technologies"],
    )

    issue_date: date = Field(
        ...,
        description=(
            "Date the certificate is issued. Accepts ISO 8601 format: YYYY-MM-DD."
        ),
        examples=["2026-10-07"],
    )

    recipients: list[RecipientInput] = Field(
        ...,
        min_length=1,
        max_length=MAX_RECIPIENTS,
        description=(
            f"List of certificate recipients. "
            f"Min 1, max {MAX_RECIPIENTS}. "
            f"Duplicate emails within the same request are rejected."
        ),
    )

    # ── Cross-field validators ─────────────────────────────────────────────────

    @field_validator("certificate_title", "course_name", "organization", mode="before")
    @classmethod
    def strip_text_fields(cls, v: object) -> object:
        """Strip whitespace from all plain-text fields."""
        if isinstance(v, str):
            return v.strip()
        return v

    @model_validator(mode="after")
    def reject_duplicate_emails(self) -> "CreateJobRequest":
        """
        Ensure no two recipients share the same email address.

        Why `model_validator(mode='after')`?
        This validator runs after ALL individual fields have been validated
        and coerced.  That means `self.recipients` is already a fully
        validated list of `RecipientInput` objects whose emails are already
        lowercased.  We can safely compare them without re-normalising.

        Alternative rejected: checking duplicates in a `field_validator` on
        `recipients` is technically possible but confusing — a field validator
        on a list receives the whole list, blurring the distinction between
        item-level and cross-item validation.
        """
        if not self.recipients:
            return self  # min_length already handles empty case

        seen: set[str] = set()
        duplicates: set[str] = set()
        for recipient in self.recipients:
            email = recipient.email  # already lowercased by RecipientInput
            if email in seen:
                duplicates.add(email)
            seen.add(email)

        if duplicates:
            raise ValueError(
                f"Duplicate recipient email(s) are not allowed in the same job: "
                f"{', '.join(sorted(duplicates))}"
            )

        return self

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "certificate_title": "Certificate of Completion",
                "course_name": "Python Backend Development",
                "organization": "ABC Technologies",
                "issue_date": "2026-10-07",
                "recipients": [
                    {"name": "Abhinav Shrimali", "email": "abhinav@example.com"},
                    {"name": "Rahul Sharma", "email": "rahul@example.com"},
                ],
            }
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────


class CreateJobResponse(BaseModel):
    """
    HTTP 202 response body returned immediately after job creation.

    The job is created and certificate records are inserted, but PDF
    generation has NOT finished.  The client should poll GET /api/jobs/{id}
    for progress.

    `Field(alias='id')` + `populate_by_name=True`
    ----------------------------------------------
    The ORM model stores the primary key as `id`, but the API contract
    exposes it as `job_id`.

    - `alias='id'` tells Pydantic: when reading from an ORM object (or dict),
      look for the key 'id' and map it to the Python attribute `job_id`.
    - `populate_by_name=True` allows BOTH `job_id=...` (Python name) and
      `id=...` (alias) when constructing the schema manually in tests.

    Result: `CreateJobResponse.model_validate(orm_job)` works automatically.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    job_id: uuid.UUID = Field(
        alias="id",
        description="Unique identifier for the created job. Use this to poll for status.",
    )
    status: JobStatus = Field(description="Initial status. Always 'PENDING'.")
    total_count: int = Field(description="Total number of recipients submitted.")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "status": "PENDING",
                "total_count": 2,
            }
        },
    )


class JobStatusResponse(BaseModel):
    """
    Response body for GET /api/jobs/{job_id}

    `pending_count` and `progress` are `@computed_field` properties.
    They are automatically included in serialisation (`.model_dump()`,
    JSON response) without needing to be stored in the database or
    set manually in the API layer.

    Why @computed_field?
    --------------------
    `@property` alone is invisible to Pydantic — it won't appear in
    `.model_dump()` or the JSON response.
    `@computed_field` wraps a property and registers it with Pydantic so
    it is treated like any other field for serialisation purposes.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    job_id: uuid.UUID = Field(alias="id", description="Job identifier.")
    status: JobStatus
    total_count: int
    completed_count: int
    failed_count: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pending_count(self) -> int:
        """
        Number of certificates still waiting to be processed.

        Derived from: total - completed - failed.
        Never negative — if somehow the counts are inconsistent, we floor at 0.
        """
        return max(0, self.total_count - self.completed_count - self.failed_count)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def progress(self) -> float:
        """
        Percentage of certificates that have reached a terminal state
        (either COMPLETED or FAILED).

        Per spec: progress = (completed + failed) / total * 100
        Failed certificates count as 'processed' for progress purposes.
        Returns 0.0 for a job with no recipients (edge case guard).
        """
        if self.total_count == 0:
            return 0.0
        processed = self.completed_count + self.failed_count
        return round(processed / self.total_count * 100, 2)

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "status": "PROCESSING",
                "total_count": 100,
                "completed_count": 73,
                "failed_count": 2,
                "pending_count": 25,
                "progress": 75.0,
            }
        },
    )


class JobCertificatesResponse(BaseModel):
    """
    Response body for GET /api/jobs/{job_id}/certificates

    Contains the job summary alongside the full list of certificate records.
    Certificate records include download URLs (set by the API layer for
    COMPLETED certificates) and error messages (for FAILED ones).
    """

    job_id: uuid.UUID = Field(description="The job these certificates belong to.")
    status: JobStatus = Field(description="Current job status.")
    total_count: int = Field(description="Total certificates in this job.")
    certificates: list["CertificateResponse"] = Field(  # noqa: F821
        description="List of all certificate records for this job."
    )


# Resolve forward reference — CertificateResponse is defined in another module.
# Import here (bottom of file) to avoid circular imports.
from app.schemas.certificate import CertificateResponse  # noqa: E402

JobCertificatesResponse.model_rebuild()
